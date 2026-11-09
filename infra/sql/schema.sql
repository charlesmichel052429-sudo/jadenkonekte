-- Système d'information — Jaden Konekté
-- PostgreSQL 16 + TimescaleDB + pgvector (chargé automatiquement au premier démarrage du volume db-data).
-- Dérivé du schéma indicatif fourni. Principales modifications :
--   * rôle global exploitant / administrateur sur utilisateur ; membre = appartenance ;
--   * contraintes d'unicité nécessaires pour associer un topic MQTT à un capteur / une vanne ;
--   * règles d'arrosage en colonnes typées (seuil, pluie, durée, délai) + journal des décisions ;
--   * motif d'invalidité des mesures, état de connexion des parcelles, cache météo.

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;          -- pgvector, pour le RAG

CREATE TABLE utilisateur (
  id            SERIAL PRIMARY KEY,
  prenom        VARCHAR(40)  NOT NULL,
  nom           VARCHAR(40)  NOT NULL,
  courriel      VARCHAR(120) NOT NULL UNIQUE,    -- stocké en minuscules
  mot_de_passe  VARCHAR(255) NOT NULL,           -- haché (Argon2id), jamais en clair
  role          VARCHAR(20)  NOT NULL DEFAULT 'exploitant'
                CHECK (role IN ('exploitant', 'administrateur')),
  actif         BOOLEAN      NOT NULL DEFAULT true,
  photo_url     VARCHAR(255),
  cree_le       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE exploitation (
  id       SERIAL PRIMARY KEY,
  code     VARCHAR(30)  NOT NULL UNIQUE,         -- utilisé dans les topics MQTT (ex. expl-1)
  nom      VARCHAR(80)  NOT NULL,
  commune  VARCHAR(80)  NOT NULL,
  lat      DOUBLE PRECISION CHECK (lat BETWEEN -90 AND 90),
  lon      DOUBLE PRECISION CHECK (lon BETWEEN -180 AND 180),
  cree_le  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Appartenance d'un utilisateur à une exploitation (base du contrôle d'accès au niveau objet)
CREATE TABLE membre (
  utilisateur   INT NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
  exploitation  INT NOT NULL REFERENCES exploitation(id) ON DELETE CASCADE,
  qualite       VARCHAR(20) NOT NULL DEFAULT 'proprietaire' CHECK (qualite IN ('proprietaire', 'membre')),
  depuis        DATE NOT NULL DEFAULT current_date,
  PRIMARY KEY (utilisateur, exploitation)
);
CREATE INDEX membre_exploitation_idx ON membre (exploitation);

CREATE TABLE parcelle (
  id            SERIAL PRIMARY KEY,
  exploitation  INT NOT NULL REFERENCES exploitation(id) ON DELETE CASCADE,
  code          VARCHAR(30) NOT NULL,            -- ex. p1 (topics MQTT)
  nom           VARCHAR(80) NOT NULL,
  culture       VARCHAR(30) NOT NULL,            -- tomate, igname, christophine…
  surface_m2    NUMERIC(10,2) CHECK (surface_m2 > 0),
  statut        VARCHAR(10) CHECK (statut IN ('online', 'offline')),  -- dernier message retenu .../statut
  statut_le     TIMESTAMPTZ,
  UNIQUE (exploitation, code)
);

CREATE TABLE capteur (
  id            SERIAL PRIMARY KEY,
  parcelle      INT NOT NULL REFERENCES parcelle(id) ON DELETE CASCADE,
  type          VARCHAR(20) NOT NULL CHECK (type IN ('sol', 'air', 'pluvio')),
  grandeur      VARCHAR(20) NOT NULL CHECK (grandeur IN ('humidite', 'temperature', 'luminosite', 'intensite')),
  unite         VARCHAR(10) NOT NULL,
  min_valide    NUMERIC,                         -- bornes de plausibilité pour la validation
  max_valide    NUMERIC,
  variation_max NUMERIC,                         -- saut maximal entre deux mesures rapprochées (NULL = pas de contrôle)
  actif         BOOLEAN NOT NULL DEFAULT true,
  UNIQUE (parcelle, type, grandeur),             -- un topic jaden/<expl>/<parcelle>/<type>/<grandeur> = un capteur
  CHECK (min_valide IS NULL OR max_valide IS NULL OR min_valide < max_valide)
);

-- Série temporelle : une ligne par mesure
CREATE TABLE mesure (
  ts        TIMESTAMPTZ NOT NULL,
  capteur   INT NOT NULL REFERENCES capteur(id) ON DELETE CASCADE,
  valeur    DOUBLE PRECISION NOT NULL,
  valide    BOOLEAN NOT NULL DEFAULT true,       -- false si aberrante (conservée pour la maintenance)
  motif     VARCHAR(30),                         -- hors_bornes, saut, unite… (NULL si valide)
  zscore    REAL,                                -- bonus : écart aux mesures récentes (|z| >= 4 : valeur inhabituelle)
  recue_le  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (capteur, ts)                      -- idempotence : un doublon MQTT (QoS 1) est ignoré
);
SELECT create_hypertable('mesure', 'ts');
-- Index partiel : graphiques et règles ne lisent que les mesures valides
CREATE INDEX mesure_valide_idx ON mesure (capteur, ts DESC) WHERE valide;

CREATE TABLE equipement (
  id              SERIAL PRIMARY KEY,
  parcelle        INT NOT NULL REFERENCES parcelle(id) ON DELETE CASCADE,
  type            VARCHAR(20) NOT NULL DEFAULT 'vanne' CHECK (type IN ('vanne')),
  etat            VARCHAR(20) NOT NULL DEFAULT 'inconnu' CHECK (etat IN ('ouverte', 'fermee', 'inconnu')),
  ouverte_jusqua  TIMESTAMPTZ,
  derniere_cmd    VARCHAR(40),
  maj_le          TIMESTAMPTZ,                   -- date du dernier état publié PAR L'OBJET
  UNIQUE (parcelle, type)                        -- une vanne par parcelle (topic .../vanne/...)
);

CREATE TABLE commande (
  id            VARCHAR(40) PRIMARY KEY,         -- identifiant envoyé dans le message MQTT
  equipement    INT NOT NULL REFERENCES equipement(id) ON DELETE CASCADE,
  action        VARCHAR(20) NOT NULL CHECK (action IN ('ouvrir', 'fermer')),
  duree_s       INT CHECK (duree_s BETWEEN 10 AND 3600),
  origine       VARCHAR(20) NOT NULL CHECK (origine IN ('manuelle', 'regle', 'agent')),
  auteur        INT REFERENCES utilisateur(id) ON DELETE SET NULL,
  statut        VARCHAR(20) NOT NULL DEFAULT 'envoyee'
                CHECK (statut IN ('envoyee', 'confirmee', 'expiree', 'echec')),
  cree_le       TIMESTAMPTZ NOT NULL DEFAULT now(),
  confirmee_le  TIMESTAMPTZ
);
CREATE INDEX commande_equipement_idx ON commande (equipement, cree_le DESC);
CREATE INDEX commande_en_attente_idx ON commande (cree_le) WHERE statut = 'envoyee';

-- Règle d'arrosage : « humidité < seuil et pluie prévue < pluie_max_mm sur horizon_h » -> ouvrir duree_s
CREATE TABLE regle (
  id                  SERIAL PRIMARY KEY,
  parcelle            INT NOT NULL REFERENCES parcelle(id) ON DELETE CASCADE,
  nom                 VARCHAR(80) NOT NULL,
  seuil_humidite      NUMERIC(5,2) NOT NULL CHECK (seuil_humidite BETWEEN 0 AND 100),
  pluie_max_mm        NUMERIC(6,2) NOT NULL DEFAULT 2 CHECK (pluie_max_mm >= 0),
  horizon_h           INT NOT NULL DEFAULT 6 CHECK (horizon_h BETWEEN 1 AND 48),
  duree_s             INT NOT NULL CHECK (duree_s BETWEEN 10 AND 3600),
  delai_min_s         INT NOT NULL DEFAULT 3600 CHECK (delai_min_s >= 0),
  active              BOOLEAN NOT NULL DEFAULT true,
  derniere_execution  TIMESTAMPTZ,               -- dernier déclenchement (sert au délai minimal)
  cree_le             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX regle_parcelle_idx ON regle (parcelle);

-- Journal : chaque évaluation d'une règle, y compris les abstentions motivées
CREATE TABLE decision (
  id               BIGSERIAL PRIMARY KEY,
  regle            INT NOT NULL REFERENCES regle(id) ON DELETE CASCADE,
  ts               TIMESTAMPTZ NOT NULL DEFAULT now(),
  declenche        BOOLEAN NOT NULL,
  motif            VARCHAR(30) NOT NULL,
  humidite         DOUBLE PRECISION,
  pluie_prevue_mm  DOUBLE PRECISION,
  source_meteo     VARCHAR(10) CHECK (source_meteo IN ('api', 'cache')),
  commande         VARCHAR(40) REFERENCES commande(id) ON DELETE SET NULL
);
CREATE INDEX decision_regle_idx ON decision (regle, ts DESC);

-- Dernières prévisions Open-Meteo par position (secours si l'API est indisponible)
CREATE TABLE meteo_cache (
  lat          NUMERIC(6,3) NOT NULL,
  lon          NUMERIC(6,3) NOT NULL,
  donnees      JSONB NOT NULL,
  obtenues_le  TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (lat, lon)
);

CREATE TABLE diagnostic (
  id            SERIAL PRIMARY KEY,
  parcelle      INT REFERENCES parcelle(id) ON DELETE SET NULL,
  auteur        INT REFERENCES utilisateur(id) ON DELETE SET NULL,
  image_chemin  VARCHAR(255),                               -- image conservée côté serveur
  statut        VARCHAR(20) NOT NULL DEFAULT 'en_cours' CHECK (statut IN ('en_cours', 'termine', 'echec')),
  classe        VARCHAR(80),
  score         REAL CHECK (score BETWEEN 0 AND 1),
  alternatives  JSONB,                                      -- classes suivantes et leurs scores
  modele        VARCHAR(60),                                -- version du modèle utilisé
  confirme      BOOLEAN,                                    -- validation par l'exploitant
  cree_le       TIMESTAMPTZ NOT NULL DEFAULT now(),
  termine_le    TIMESTAMPTZ
);
CREATE INDEX diagnostic_auteur_idx ON diagnostic (auteur, cree_le DESC);
CREATE INDEX diagnostic_parcelle_idx ON diagnostic (parcelle, cree_le DESC);

-- Réseau régional d'alertes (bonus) : alertes publiées par la plateforme (locale) ou reçues par webhook (reseau)
CREATE TABLE alerte (
  id          VARCHAR(40) PRIMARY KEY,                  -- id du serveur central (alt_…) ; loc-<diagnostic> si non publiée
  origine     VARCHAR(20) NOT NULL CHECK (origine IN ('locale', 'reseau')),
  statut      VARCHAR(20) NOT NULL DEFAULT 'recue' CHECK (statut IN ('publiee', 'echec', 'recue')),
  diagnostic  INT UNIQUE REFERENCES diagnostic(id) ON DELETE SET NULL,   -- un diagnostic confirmé = une alerte
  emetteur    VARCHAR(80),
  type        VARCHAR(20) NOT NULL,
  culture     VARCHAR(30),
  maladie     VARCHAR(80),
  gravite     VARCHAR(10),
  commune     VARCHAR(80),
  contenu     JSONB NOT NULL,
  recue_le    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX alerte_recue_idx ON alerte (recue_le DESC);

-- Inscription de la plateforme auprès du serveur central (une seule ligne). Le jeton n'est renvoyé
-- qu'une fois par le serveur central : il est conservé ici, jamais exposé par l'API.
CREATE TABLE reseau_inscription (
  id           VARCHAR(40) PRIMARY KEY,                 -- plt_… attribué par le serveur central
  central_url  VARCHAR(255) NOT NULL,
  groupe       VARCHAR(40) NOT NULL,
  jeton        VARCHAR(255) NOT NULL,
  inscrite_le  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE historique (
  id           BIGSERIAL PRIMARY KEY,
  ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
  exploitation INT REFERENCES exploitation(id) ON DELETE CASCADE,
  utilisateur  INT REFERENCES utilisateur(id) ON DELETE SET NULL,
  type         VARCHAR(30) NOT NULL,                    -- connexion, commande, regle, diagnostic…
  details      JSONB
);
CREATE INDEX historique_exploitation_idx ON historique (exploitation, ts DESC);

-- Passages des fiches techniques pour le RAG (384 = paraphrase-multilingual-MiniLM-L12-v2)
CREATE TABLE passage (
  id          SERIAL PRIMARY KEY,
  source      VARCHAR(120) NOT NULL,                    -- nom du fichier
  section     VARCHAR(200),
  contenu     TEXT NOT NULL,
  embedding   vector(384),
  -- recherche plein texte (stemming français), combinée à la recherche vectorielle : recherche hybride.
  -- Le titre de section pèse plus (A) que le texte (B) : « mildiou » doit d'abord trouver la section Mildiou.
  tsv         tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('french', coalesce(section, '')), 'A') ||
                setweight(to_tsvector('french', contenu), 'B')) STORED,
  UNIQUE (source, section)
);
CREATE INDEX passage_embedding_idx ON passage USING hnsw (embedding vector_cosine_ops);
CREATE INDEX passage_tsv_idx ON passage USING gin (tsv);
