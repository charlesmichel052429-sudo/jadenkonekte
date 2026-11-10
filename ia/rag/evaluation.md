# Évaluation de l'assistant agronome

LLM : `openai/gpt-oss-120b` (Groq) · recherche hybride (vecteurs + plein texte) · seuil de similarité 0.35

**15/20 réponses jugées réussies** par les critères automatiques.

| # | Question | Fiche attendue | Recherche | Citée | Éléments | Durée | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Quand faut-il arroser les tomates dans la journée ? | 01_tomate_culture.md | oui | oui | 1/2 | 8.6 s | **réussi** |
| 2 | Pourquoi mes tomates ont une tache noire sous le fruit ? | 01_tomate_culture.md | oui | non | 0/3 | 3.3 s | **à revoir** |
| 3 | Combien de temps attendre avant de replanter des tomates au même endroit ? | 01_tomate_culture.md | oui | oui | 2/3 | 2.6 s | **réussi** |
| 4 | Comment reconnaître le mildiou sur la tomate ? | 02_tomate_maladies.md | oui | oui | 2/2 | 2.5 s | **réussi** |
| 5 | Quel insecte transmet le virus des feuilles jaunes en cuillère ? | 02_tomate_maladies.md | oui | oui | 2/2 | 3.6 s | **réussi** |
| 6 | Existe-t-il un traitement contre le TYLCV ? | 02_tomate_maladies.md | oui | oui | 2/2 | 2.3 s | **réussi** |
| 7 | Comment éviter la propagation du virus de la mosaïque ? | 02_tomate_maladies.md | oui | oui | 3/3 | 3.4 s | **réussi** |
| 8 | Ma plante de tomate flétrit d'un coup mais les feuilles restent vertes, qu'est-ce que c'est ? | 02_tomate_maladies.md | oui | oui | 1/3 | 3.2 s | **à revoir** |
| 9 | Quelles conditions favorisent les acariens ? | 02_tomate_maladies.md | oui | oui | 1/2 | 4.3 s | **réussi** |
| 10 | Quelle est la principale maladie de l'igname aux Antilles ? | 03_igname.md | oui | oui | 2/2 | 2.3 s | **réussi** |
| 11 | Pourquoi planter l'igname sur buttes ? | 03_igname.md | oui | oui | 1/2 | 12.8 s | **réussi** |
| 12 | Quand arrêter d'arroser l'igname ? | 03_igname.md | oui | oui | 2/2 | 2.0 s | **réussi** |
| 13 | Comment planter une christophine ? | 04_christophine.md | oui | oui | 2/2 | 2.7 s | **réussi** |
| 14 | La christophine supporte-t-elle l'eau stagnante ? | 04_christophine.md | oui | oui | 1/3 | 5.0 s | **à revoir** |
| 15 | Mon capteur indique 999 % d'humidité, faut-il arrêter l'arrosage ? | 05_irrigation_sol.md | oui | oui | 0/2 | 2.3 s | **à revoir** |
| 16 | À partir de quelle humidité du sol faut-il arroser ? | 05_irrigation_sol.md | oui | oui | 2/3 | 22.8 s | **réussi** |
| 17 | Faut-il arroser si une averse est prévue ? | 05_irrigation_sol.md | oui | oui | 0/2 | 3.4 s | **à revoir** |
| 18 | Le modèle détecte du mildiou avec un score de 0,55 : que faire ? | 06_protocole_alerte.md | oui | oui | 4/4 | 5.3 s | **réussi** |
| 19 | Quand publier une alerte sur le réseau régional ? | 06_protocole_alerte.md | oui | oui | 1/1 | 3.0 s | **réussi** |
| 20 | Quelle est la dose de fongicide à utiliser contre le mildiou ? | hors corpus | — | — | — | 1.8 s | **réussi** |

## Réponses complètes

### 1. Quand faut-il arroser les tomates dans la journée ?

*Attendu : tôt le matin ou en fin d'après-midi, au pied*  
*Sources transmises : [1] 01_tomate_culture.md › Conditions de culture; [2] 01_tomate_culture.md › Besoins en eau; [3] 01_tomate_culture.md › Implantation; [4] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV)*

> Il est recommandé d’arroser les tomates tôt le matin ou en fin d’après‑midi, afin de limiter l’évaporation. [2]

### 2. Pourquoi mes tomates ont une tache noire sous le fruit ?

*Attendu : nécrose apicale, arrosage irrégulier, calcium*  
*Sources transmises : [1] 02_tomate_maladies.md › Septoriose; [2] 02_tomate_maladies.md › Corynesporiose (tache cible); [3] 02_tomate_maladies.md › Gale bactérienne (tache bactérienne); [4] 01_tomate_culture.md › Implantation*

> La présence de petites pustules sombres (liégeuses) sur les fruits de tomate correspond à la **gale bactérienne**. Cette maladie se manifeste par de petites taches humides qui se nécrosent, puis forment des pustules sur les fruits, souvent de couleur sombre [3].  
> 
> **Prévention** :  
> - Utiliser des plants sains [3]  
> - Arroser au pied pour éviter les éclaboussures [3]  
> - Désinfecter les outils de travail [3]

### 3. Combien de temps attendre avant de replanter des tomates au même endroit ?

*Attendu : trois à quatre ans, rotation, solanacées*  
*Sources transmises : [1] 01_tomate_culture.md › Implantation; [2] 01_tomate_culture.md › Surveillance; [3] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV); [4] 02_tomate_maladies.md › Acariens (tétranyque tisserand)*

> Il faut attendre trois à quatre ans avant de replanter des tomates (ou d’autres solanacées) au même endroit[1].

### 4. Comment reconnaître le mildiou sur la tomate ?

*Attendu : taches huileuses brun-vert, duvet blanc au revers*  
*Sources transmises : [1] 01_tomate_culture.md › Surveillance; [2] 01_tomate_culture.md › Implantation; [3] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV); [4] 02_tomate_maladies.md › Mildiou*

> Le mildiou se manifeste sur la tomate par :
> 
> - de grandes taches brun‑vert d’aspect huileux sur les feuilles,  
> - un duvet blanchâtre au revers des feuilles lorsqu’il fait humide,  
> - un brunissement des tiges et des fruits, avec une évolution très rapide de la maladie.  
> 
> [4]

### 5. Quel insecte transmet le virus des feuilles jaunes en cuillère ?

*Attendu : aleurode, Bemisia tabaci*  
*Sources transmises : [1] 02_tomate_maladies.md › Virus des feuilles jaunes en cuillère (TYLCV); [2] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV); [3] 01_tomate_culture.md › Surveillance; [4] 02_tomate_maladies.md › Septoriose*

> L’insecte vecteur du virus des feuilles jaunes en cuillère (TYLCV) est l’aleurode, communément appelée mouche blanche (*Bemisia tabaci*)[1].

### 6. Existe-t-il un traitement contre le TYLCV ?

*Attendu : pas de traitement curatif ; prévention*  
*Sources transmises : [1] 02_tomate_maladies.md › Virus des feuilles jaunes en cuillère (TYLCV); [2] 02_tomate_maladies.md › Présentation de la fiche*

> Il n’existe pas de traitement curatif contre le virus des feuilles jaunes en cuillère (TYLCV) ; la lutte repose sur la prévention (variétés tolérantes, filets anti‑insectes, désherbage, arrachage des plants atteints)[1].

### 7. Comment éviter la propagation du virus de la mosaïque ?

*Attendu : mains, outils désinfectés, éliminer les plants*  
*Sources transmises : [1] 06_protocole_alerte.md › 2. Limiter la propagation sur l'exploitation; [2] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV); [3] 02_tomate_maladies.md › Virus des feuilles jaunes en cuillère (TYLCV); [4] 06_protocole_alerte.md › 3. Prévenir le voisinage*

> - Retirer et évacuer immédiatement les feuilles ou plants atteints, sans les laisser au sol ni les composter.  
> - Désinfecter soigneusement les outils et se laver les mains après chaque manipulation.  
> - Éviter l’arrosage par aspersion et ne pas circuler dans la parcelle mouillée afin de limiter les contacts.  
> - Éliminer les plants contaminés dès l’apparition des symptômes.  
> 
> Ces mesures sont décrites dans les fiches techniques : retrait et évacuation des parties infectées, désinfection des outils et des mains, suspension de l’arrosage par aspersion [1] ; prévention par lavage des mains, désinfection des outils et élimination des plants atteints [2].

### 8. Ma plante de tomate flétrit d'un coup mais les feuilles restent vertes, qu'est-ce que c'est ?

*Attendu : flétrissement bactérien, Ralstonia, non détecté par le modèle*  
*Sources transmises : [1] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV); [2] 02_tomate_maladies.md › Flétrissement bactérien (à connaître, non détecté par le modèle); [3] 01_tomate_culture.md › Implantation; [4] 01_tomate_culture.md › Surveillance*

> Il s’agit très probablement d’un flétrissement bactérien, caractérisé par un flétrissement brutal de la plante alors que les feuilles restent vertes, avec parfois un exsudat laiteux à la coupe de la tige [2].

### 9. Quelles conditions favorisent les acariens ?

*Attendu : temps chaud et sec, stress hydrique*  
*Sources transmises : [1] 02_tomate_maladies.md › Acariens (tétranyque tisserand); [2] 01_tomate_culture.md › Besoins en eau; [3] 03_igname.md › Anthracnose; [4] 01_tomate_culture.md › Conditions de culture*

> Les acariens (tétranyque tisserand) se développent surtout par temps chaud et sec, et lorsque les plantes sont stressées par un manque d’eau [1].

### 10. Quelle est la principale maladie de l'igname aux Antilles ?

*Attendu : anthracnose, Colletotrichum gloeosporioides*  
*Sources transmises : [1] 03_igname.md › Généralités; [2] 03_igname.md › Anthracnose; [3] 02_tomate_maladies.md › Flétrissement bactérien (à connaître, non détecté par le modèle); [4] 06_protocole_alerte.md › 3. Prévenir le voisinage*

> La principale maladie de l’igname aux Antilles est l’anthracnose, causée par le champignon *Colletotrichum gloeosporioides* [2].

### 11. Pourquoi planter l'igname sur buttes ?

*Attendu : éviter l'excès d'eau, pourriture des tubercules*  
*Sources transmises : [1] 04_christophine.md › Plantation; [2] 03_igname.md › Plantation; [3] 03_igname.md › Généralités; [4] 03_igname.md › Récolte et conservation*

> Planter l’igname sur des buttes ou des billons permet d’éviter l’excès d’eau au niveau des tubercules, ce qui prévient leur détérioration. [2]

### 12. Quand arrêter d'arroser l'igname ?

*Attendu : fin de cycle, feuillage jaunit*  
*Sources transmises : [1] 03_igname.md › Besoins en eau; [2] 05_irrigation_sol.md › Seuils indicatifs pour le projet*

> Il faut cesser l’arrosage dès que le feuillage commence à jaunir naturellement en fin de cycle ; à ce stade, réduisez l’irrigation puis arrêtez‑la complètement [1].  
> De plus, tant que l’humidité du sol reste dans la zone « confort hydrique » (30 %–45 %) ou supérieure (> 45 %), il n’est pas nécessaire d’arroser [2].

### 13. Comment planter une christophine ?

*Attendu : fruit germé à moitié enterré, treille*  
*Sources transmises : [1] 04_christophine.md › Plantation; [2] 03_igname.md › Plantation; [3] 04_christophine.md › Généralités; [4] 01_tomate_culture.md › Implantation*

> Pour planter une christophine :
> 
> - Plantez le fruit entier, déjà germé, à moitié enterré dans le sol, la pointe dirigée vers le haut.  
> - Prévoyez une treille ou une tonnelle solide, car la plante est très vigoureuse et grimpe.  
> - Choisissez un emplacement frais et humide (souvent en altitude) avec un sol riche en matière organique.  
> 
> [1]

### 14. La christophine supporte-t-elle l'eau stagnante ?

*Attendu : non, pourriture du collet, sol drainé*  
*Sources transmises : [1] 04_christophine.md › Besoins en eau; [2] 03_igname.md › Besoins en eau; [3] 01_tomate_culture.md › Besoins en eau; [4] 05_irrigation_sol.md › Comprendre la mesure*

> Non, la christophine ne supporte pas l'eau stagnante, qui fait pourrir le collet. [1]

### 15. Mon capteur indique 999 % d'humidité, faut-il arrêter l'arrosage ?

*Attendu : valeur aberrante, panne du capteur*  
*Sources transmises : [1] 05_irrigation_sol.md › Bonnes pratiques d'arrosage; [2] 05_irrigation_sol.md › Seuils indicatifs pour le projet; [3] 05_irrigation_sol.md › Saisons; [4] 05_irrigation_sol.md › Exemple de règle automatique*

> Oui, il faut arrêter l’arrosage : une valeur supérieure à 100 % (comme 999 %) indique une anomalie du capteur, pas un sol très humide [1].

### 16. À partir de quelle humidité du sol faut-il arroser ?

*Attendu : 20-30 % si pas de pluie prévue, < 20 % rapidement ; seuils indicatifs*  
*Sources transmises : [1] 05_irrigation_sol.md › Comprendre la mesure; [2] 05_irrigation_sol.md › Exemple de règle automatique; [3] 05_irrigation_sol.md › Seuils indicatifs pour le projet; [4] 05_irrigation_sol.md › Bonnes pratiques d'arrosage*

> Il faut arroser lorsque l’humidité du sol descend en dessous de 30 % :  
> 
> - **20 % – 30 %** : arroser si aucune pluie n’est prévue.  
> - **< 20 %** : arroser rapidement, le sol est sec et la plante est stressée.  
> 
> [3]

### 17. Faut-il arroser si une averse est prévue ?

*Attendu : non, tenir compte de la météo*  
*Sources transmises : [1] 05_irrigation_sol.md › Bonnes pratiques d'arrosage; [2] 05_irrigation_sol.md › Saisons; [3] 05_irrigation_sol.md › Exemple de règle automatique; [4] 05_irrigation_sol.md › Seuils indicatifs pour le projet*

> Non, il ne faut pas arroser si une pluie significative est prévue dans les prochaines heures ; c’est l’intérêt d’une API météo. [1]

### 18. Le modèle détecte du mildiou avec un score de 0,55 : que faire ?

*Attendu : score < 0,7 : reprendre des photos, comparer, technicien*  
*Sources transmises : [1] 06_protocole_alerte.md › 1. Confirmer le diagnostic; [2] 06_protocole_alerte.md › Présentation de la fiche; [3] 02_tomate_maladies.md › Flétrissement bactérien (à connaître, non détecté par le modèle); [4] 05_irrigation_sol.md › Présentation de la fiche*

> Le modèle indique un score de confiance inférieur à 0,7, il faut donc :
> 
> - Reprendre une ou plusieurs nouvelles photos : une feuille entière, bien éclairée, sur fond neutre ; puis relancer le diagnostic [1]  
> - Comparer les symptômes observés avec la description de la fiche « Tomate — maladies et ravageurs » pour vérifier s’il s’agit bien de mildiou [1]  
> - En cas de doute persistant, solliciter l’avis d’un technicien agricole [1]

### 19. Quand publier une alerte sur le réseau régional ?

*Attendu : après confirmation par l'exploitant*  
*Sources transmises : [1] 06_protocole_alerte.md › 3. Prévenir le voisinage*

> Une alerte n’est publiée sur le réseau régional qu’après **confirmation** du problème par l’exploitant de la parcelle concernée[1].

### 20. Quelle est la dose de fongicide à utiliser contre le mildiou ?

*Attendu : hors du corpus : l'assistant doit refuser de donner une dose et orienter vers un conseiller*  
*Sources transmises : [1] 02_tomate_maladies.md › Présentation de la fiche; [2] 02_tomate_maladies.md › Mildiou*

> Je ne trouve pas cette information dans les fiches techniques. Je vous recommande de consulter un conseiller agricole ou un technicien spécialisé pour obtenir la dose appropriée de fongicide contre le mildiou.


## Relecture des réponses (2026-11-10)

Les critères automatiques recherchent des mots-clés ; les cinq réponses marquées « à revoir » ont été relues :

| # | Constat à la lecture | Verdict final |
|---|---|---|
| 2 | Le passage « Besoins en eau » (nécrose apicale) n'a pas été retrouvé ; la réponse attribue la tache à la gale bactérienne. | **fausse** |
| 8 | Identifie le flétrissement bactérien et cite la bonne section ; ne mentionne ni *Ralstonia solanacearum* ni le fait que le CNN ne le détecte pas. | correcte, incomplète |
| 14 | « Non… fait pourrir le collet », source citée ; ne rappelle pas la nécessité d'un sol drainé. | correcte, incomplète |
| 15 | Reconnaît une anomalie du capteur (valeur supérieure à 100 %) ; le « oui, il faut arrêter » est discutable, la fiche demande surtout d'ignorer la valeur. | correcte, formulation discutable |
| 17 | « Non, il ne faut pas arroser si une pluie significative est prévue », source citée. Faux négatif du critère automatique. | correcte |

**Bilan relu : 19/20 réponses exactes et sourcées**, dont 2 incomplètes et 1 à la formulation discutable ; la question
hors corpus (dose de fongicide) est déclinée sans aucune dose inventée.

L'erreur de la question 2 vient de la recherche : le modèle d'embeddings est utilisé dans sa version quantifiée
(118 Mo au lieu de 470 Mo) pour limiter la taille du service d'inférence, et la question (« tache noire sous le
fruit ») ne partage presque aucun mot avec le passage attendu, donc la recherche plein texte ne compense pas.

Limites : 20 questions proches du vocabulaire des fiches ; une seule exécution (le LLM n'est pas strictement
déterministe) ; quota gratuit Groq, d'où une pause de 8 s entre les questions.
