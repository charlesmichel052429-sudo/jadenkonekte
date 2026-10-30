# Évaluation de l'assistant agronome

LLM : `groq/openai/gpt-oss-120b` · embeddings : `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` · 38 passages · seuil cosinus 0.35 · recherche hybride (vecteurs + plein texte)

**17/20 réponses jugées réussies** (critères automatiques, à confirmer à la lecture).

| # | Question | Fiche attendue | Recherche | Citée | Éléments | Durée | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Quand faut-il arroser les tomates dans la journée ? | 01_tomate_culture.md | oui | oui | 1/2 | 3.6 s | **réussi** |
| 2 | Pourquoi mes tomates ont une tache noire sous le fruit ? | 01_tomate_culture.md | oui | oui | 2/3 | 5.3 s | **réussi** |
| 3 | Combien de temps attendre avant de replanter des tomates au même endroit ? | 01_tomate_culture.md | oui | oui | 2/3 | 7.0 s | **réussi** |
| 4 | Comment reconnaître le mildiou sur la tomate ? | 02_tomate_maladies.md | oui | oui | 2/2 | 1.0 s | **réussi** |
| 5 | Quel insecte transmet le virus des feuilles jaunes en cuillère ? | 02_tomate_maladies.md | oui | oui | 2/2 | 1.3 s | **réussi** |
| 6 | Existe-t-il un traitement contre le TYLCV ? | 02_tomate_maladies.md | oui | oui | 2/2 | 1.0 s | **réussi** |
| 7 | Comment éviter la propagation du virus de la mosaïque ? | 02_tomate_maladies.md | oui | oui | 3/3 | 1.9 s | **réussi** |
| 8 | Ma plante de tomate flétrit d'un coup mais les feuilles restent vertes, qu'est-ce que c'est ? | 02_tomate_maladies.md | oui | oui | 1/3 | 4.4 s | **à revoir** |
| 9 | Quelles conditions favorisent les acariens ? | 02_tomate_maladies.md | oui | oui | 1/2 | 2.5 s | **réussi** |
| 10 | Quelle est la principale maladie de l'igname aux Antilles ? | 03_igname.md | oui | oui | 2/2 | 0.9 s | **réussi** |
| 11 | Pourquoi planter l'igname sur buttes ? | 03_igname.md | oui | oui | 2/2 | 1.4 s | **réussi** |
| 12 | Quand arrêter d'arroser l'igname ? | 03_igname.md | oui | oui | 2/2 | 1.8 s | **réussi** |
| 13 | Comment planter une christophine ? | 04_christophine.md | oui | oui | 2/2 | 5.5 s | **réussi** |
| 14 | La christophine supporte-t-elle l'eau stagnante ? | 04_christophine.md | oui | oui | 1/3 | 2.5 s | **à revoir** |
| 15 | Mon capteur indique 999 % d'humidité, faut-il arrêter l'arrosage ? | 05_irrigation_sol.md | oui | oui | 2/2 | 5.1 s | **réussi** |
| 16 | À partir de quelle humidité du sol faut-il arroser ? | 05_irrigation_sol.md | oui | oui | 2/3 | 2.5 s | **réussi** |
| 17 | Faut-il arroser si une averse est prévue ? | 05_irrigation_sol.md | oui | oui | 0/2 | 2.3 s | **à revoir** |
| 18 | Le modèle détecte du mildiou avec un score de 0,55 : que faire ? | 06_protocole_alerte.md | oui | oui | 4/4 | 1.3 s | **réussi** |
| 19 | Quand publier une alerte sur le réseau régional ? | 06_protocole_alerte.md | oui | oui | 1/1 | 3.2 s | **réussi** |
| 20 | Quelle est la dose de fongicide à utiliser contre le mildiou ? | hors corpus | — | — | — | 1.3 s | **réussi** |

## Réponses complètes

### 1. Quand faut-il arroser les tomates dans la journée ?

*Attendu : tôt le matin ou en fin d'après-midi, au pied*  
*Sources transmises : [1] 01_tomate_culture.md › Besoins en eau (0.665); [2] 01_tomate_culture.md › Conditions de culture (0.644); [3] 01_tomate_culture.md › Implantation (0.637); [4] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV) (0.468)*

> Il faut arroser les tomates tôt le matin ou en fin d’après‑midi, afin de limiter l’évaporation. [1]

### 2. Pourquoi mes tomates ont une tache noire sous le fruit ?

*Attendu : nécrose apicale, arrosage irrégulier, calcium*  
*Sources transmises : [1] 01_tomate_culture.md › Besoins en eau (0.648); [2] 02_tomate_maladies.md › Septoriose (0.633); [3] 02_tomate_maladies.md › Corynesporiose (tache cible) (0.541); [4] 02_tomate_maladies.md › Gale bactérienne (tache bactérienne) (0.511)*

> La tache noire à la base du fruit (nécrose apicale) apparaît lorsque le sol subit des à‑coups d’humidité : un sol très sec puis très humide empêche une bonne alimentation en calcium du fruit, ce qui provoque cette nécrose [1].

### 3. Combien de temps attendre avant de replanter des tomates au même endroit ?

*Attendu : trois à quatre ans, rotation, solanacées*  
*Sources transmises : [1] 01_tomate_culture.md › Implantation (0.701); [2] 01_tomate_culture.md › Surveillance (0.58); [3] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV) (0.401); [4] 02_tomate_maladies.md › Acariens (tétranyque tisserand) (0.434)*

> Il faut attendre trois à quatre ans avant de replanter des tomates (ou d’autres solanacées) au même endroit[1].

### 4. Comment reconnaître le mildiou sur la tomate ?

*Attendu : taches huileuses brun-vert, duvet blanc au revers*  
*Sources transmises : [1] 01_tomate_culture.md › Surveillance (0.702); [2] 01_tomate_culture.md › Besoins en eau (0.642); [3] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV) (0.543); [4] 02_tomate_maladies.md › Mildiou (0.526)*

> Le mildiou se manifeste sur la tomate par :
> 
> - de grandes taches brun‑vert d’aspect huileux sur les feuilles,  
> - un duvet blanchâtre qui apparaît au revers des feuilles quand l’air est humide,  
> - un brunissement des tiges et des fruits, avec une évolution très rapide de la maladie.  
> 
> Ces signes apparaissent surtout en présence d’humidité élevée et de feuillage mouillé longtemps [4].

### 5. Quel insecte transmet le virus des feuilles jaunes en cuillère ?

*Attendu : aleurode, Bemisia tabaci*  
*Sources transmises : [1] 02_tomate_maladies.md › Virus des feuilles jaunes en cuillère (TYLCV) (0.602); [2] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV) (0.537); [3] 01_tomate_culture.md › Surveillance (0.468); [4] 03_igname.md › Anthracnose (0.472)*

> L’insecte vecteur du virus des feuilles jaunes en cuillère (TYLCV) est l’aleurode — la mouche blanche (*Bemisia tabaci*)[1].

### 6. Existe-t-il un traitement contre le TYLCV ?

*Attendu : pas de traitement curatif ; prévention*  
*Sources transmises : [1] 02_tomate_maladies.md › Virus des feuilles jaunes en cuillère (TYLCV) (0.372); [2] 02_tomate_maladies.md › Présentation de la fiche (0.175)*

> Non, il n’existe pas de traitement curatif contre le virus des feuilles jaunes en cuillère (TYLCV) ; la lutte repose sur la prévention (variétés tolérantes, filets anti‑insectes, désherbage, arrachage des plants atteints)[1].

### 7. Comment éviter la propagation du virus de la mosaïque ?

*Attendu : mains, outils désinfectés, éliminer les plants*  
*Sources transmises : [1] 06_protocole_alerte.md › 2. Limiter la propagation sur l'exploitation (0.546); [2] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV) (0.512); [3] 02_tomate_maladies.md › Virus des feuilles jaunes en cuillère (TYLCV) (0.503); [4] 06_protocole_alerte.md › 3. Prévenir le voisinage (0.523)*

> - Retirer et évacuer immédiatement les feuilles ou plants atteints, sans les laisser au sol ni les composter.  
> - Désinfecter soigneusement les outils et se laver les mains après chaque manipulation.  
> - Éviter le contact entre les plants sains et les parties infectées (pas d’arrosage par aspersion, ne pas circuler dans la parcelle mouillée).  
> - Éliminer les plants contaminés dès les premiers signes.  
> 
> Ces mesures limitent la propagation du virus de la mosaïque de la tomate, qui se transmet par contact direct (mains, outils, semences) et est très résistant dans l’environnement. [1][2]

### 8. Ma plante de tomate flétrit d'un coup mais les feuilles restent vertes, qu'est-ce que c'est ?

*Attendu : flétrissement bactérien, Ralstonia, non détecté par le modèle*  
*Sources transmises : [1] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV) (0.62); [2] 02_tomate_maladies.md › Flétrissement bactérien (à connaître, non détecté par le modèle) (0.604); [3] 01_tomate_culture.md › Implantation (0.635); [4] 01_tomate_culture.md › Surveillance (0.661)*

> Il s’agit très probablement d’un flétrissement bactérien, caractérisé par un flétrissement brutal de la plante alors que les feuilles restent vertes, avec parfois un exsudat laiteux à la coupe de la tige [2].

### 9. Quelles conditions favorisent les acariens ?

*Attendu : temps chaud et sec, stress hydrique*  
*Sources transmises : [1] 02_tomate_maladies.md › Acariens (tétranyque tisserand) (0.477); [2] 03_igname.md › Récolte et conservation (0.446); [3] 04_christophine.md › Problèmes courants (0.463); [4] 01_tomate_culture.md › Conditions de culture (0.314)*

> Les acariens (tétranyque tisserand) se développent surtout par temps chaud et sec, et lorsque les plantes sont stressées par un manque d’eau[1].

### 10. Quelle est la principale maladie de l'igname aux Antilles ?

*Attendu : anthracnose, Colletotrichum gloeosporioides*  
*Sources transmises : [1] 03_igname.md › Anthracnose (0.483); [2] 03_igname.md › Généralités (0.452); [3] 02_tomate_maladies.md › Flétrissement bactérien (à connaître, non détecté par le modèle) (0.389); [4] 06_protocole_alerte.md › 4. Signaler si nécessaire (0.398)*

> La principale maladie de l’igname aux Antilles est l’anthracnose, causée par le champignon *Colletotrichum gloeosporioides*[1].

### 11. Pourquoi planter l'igname sur buttes ?

*Attendu : éviter l'excès d'eau, pourriture des tubercules*  
*Sources transmises : [1] 03_igname.md › Plantation (0.305); [2] 04_christophine.md › Plantation (0.327); [3] 03_igname.md › Récolte et conservation (0.33); [4] 03_igname.md › Généralités (0.214)*

> Planter l’igname sur des buttes ou des billons permet d’éviter l’excès d’eau au niveau des tubercules, ce qui réduit le risque de pourriture et favorise un bon développement. [1]

### 12. Quand arrêter d'arroser l'igname ?

*Attendu : fin de cycle, feuillage jaunit*  
*Sources transmises : [1] 03_igname.md › Besoins en eau (0.062); [2] 05_irrigation_sol.md › Seuils indicatifs pour le projet (-0.014)*

> L’igname doit être arrosée pendant sa phase de croissance active, puis, en fin de cycle, le feuillage jaunit naturellement ; il faut alors réduire l’arrosage et l’arrêter complètement dès que le jaunissement apparaît [1].  
> 
> De façon plus générale, si l’humidité du sol dépasse 45 % (sol très humide, proche de la saturation), il ne faut plus arroser [2].

### 13. Comment planter une christophine ?

*Attendu : fruit germé à moitié enterré, treille*  
*Sources transmises : [1] 04_christophine.md › Plantation (0.428); [2] 03_igname.md › Plantation (0.508); [3] 04_christophine.md › Généralités (0.349); [4] 03_igname.md › Récolte et conservation (0.452)*

> Pour planter une christophine :  
> - Plantez le fruit entier, déjà germé, à moitié enterré dans le sol, la pointe dirigée vers le haut [1].  
> - Prévoyez un support solide (treille ou tonnelle) car la plante est très vigoureuse [1].  
> - Choisissez un emplacement frais et humide, idéalement en altitude, avec un sol riche en matière organique [1].

### 14. La christophine supporte-t-elle l'eau stagnante ?

*Attendu : non, pourriture du collet, sol drainé*  
*Sources transmises : [1] 04_christophine.md › Besoins en eau (0.699); [2] 03_igname.md › Besoins en eau (0.664); [3] 01_tomate_culture.md › Besoins en eau (0.508); [4] 04_christophine.md › Plantation (0.426)*

> Non, la christophine ne supporte pas l'eau stagnante ; cela fait pourrir le collet. [1]

### 15. Mon capteur indique 999 % d'humidité, faut-il arrêter l'arrosage ?

*Attendu : valeur aberrante, panne du capteur*  
*Sources transmises : [1] 05_irrigation_sol.md › Seuils indicatifs pour le projet (0.454); [2] 05_irrigation_sol.md › Bonnes pratiques d'arrosage (0.452); [3] 05_irrigation_sol.md › Saisons (0.482); [4] 05_irrigation_sol.md › Exemple de règle automatique (0.563)*

> Oui, il faut arrêter l’arrosage : une valeur de 999 % est aberrante et signale une panne du capteur, pas un sol très humide. [2]

### 16. À partir de quelle humidité du sol faut-il arroser ?

*Attendu : 20-30 % si pas de pluie prévue, < 20 % rapidement ; seuils indicatifs*  
*Sources transmises : [1] 05_irrigation_sol.md › Seuils indicatifs pour le projet (0.665); [2] 05_irrigation_sol.md › Comprendre la mesure (0.737); [3] 05_irrigation_sol.md › Exemple de règle automatique (0.774); [4] 05_irrigation_sol.md › Bonnes pratiques d'arrosage (0.633)*

> Il faut arroser dès que l’humidité du sol descend en dessous de 30 % :  
> - entre 20 % et 30 % : arroser si aucune pluie n’est prévue ;  
> - en dessous de 20 % : arroser rapidement. [1]

### 17. Faut-il arroser si une averse est prévue ?

*Attendu : non, tenir compte de la météo*  
*Sources transmises : [1] 05_irrigation_sol.md › Bonnes pratiques d'arrosage (0.493); [2] 05_irrigation_sol.md › Seuils indicatifs pour le projet (0.377); [3] 05_irrigation_sol.md › Exemple de règle automatique (0.465); [4] 05_irrigation_sol.md › Saisons (0.427)*

> Non, il ne faut pas arroser si une pluie significative est prévue dans les prochaines heures ; c’est l’intérêt d’une API météo. [1]

### 18. Le modèle détecte du mildiou avec un score de 0,55 : que faire ?

*Attendu : score < 0,7 : reprendre des photos, comparer, technicien*  
*Sources transmises : [1] 06_protocole_alerte.md › 1. Confirmer le diagnostic (0.394); [2] 06_protocole_alerte.md › Présentation de la fiche (0.322); [3] 02_tomate_maladies.md › Flétrissement bactérien (à connaître, non détecté par le modèle) (0.093); [4] 05_irrigation_sol.md › Présentation de la fiche (0.371)*

> Le modèle indique un score de confiance inférieur à 0,7 ; il faut donc :
> 
> - Reprendre une ou plusieurs nouvelles photos (feuille entière, bien éclairée, fond neutre) pour améliorer la qualité de l’image [1]  
> - Comparer les nouvelles images avec la description des symptômes figurant dans la fiche « Tomate — maladies et ravageurs » [1]  
> - En cas de doute persistant, solliciter l’avis d’un technicien agricole [1]

### 19. Quand publier une alerte sur le réseau régional ?

*Attendu : après confirmation par l'exploitant*  
*Sources transmises : [1] 06_protocole_alerte.md › 3. Prévenir le voisinage (0.474)*

> Une alerte n’est publiée sur le réseau régional qu’après **confirmation** de la maladie ou du vecteur par l’exploitant concerné[1].

### 20. Quelle est la dose de fongicide à utiliser contre le mildiou ?

*Attendu : hors du corpus : l'assistant doit refuser de donner une dose et orienter vers un conseiller*  
*Sources transmises : [1] 02_tomate_maladies.md › Présentation de la fiche (0.303); [2] 02_tomate_maladies.md › Mildiou (0.241)*

> Je ne trouve pas cette information dans les fiches techniques. Je vous recommande de consulter un conseiller agricole ou un technicien spécialisé pour obtenir la dose appropriée de fongicide contre le mildiou.


## Relecture humaine (2026-10-30)

Les critères automatiques recherchent des mots-clés ; trois réponses marquées « à revoir » ont été relues :

| # | Constat à la lecture | Verdict final |
|---|---|---|
| 8 | Identifie correctement le flétrissement bactérien (flétrissement brutal, feuilles vertes, exsudat laiteux) et cite la bonne section ; ne mentionne ni *Ralstonia solanacearum* ni le fait que le CNN ne le détecte pas. | correcte, incomplète |
| 14 | « Non… cela fait pourrir le collet », source citée ; ne rappelle pas la nécessité d'un sol drainé. | correcte, incomplète |
| 17 | « Non, il ne faut pas arroser si une pluie significative est prévue », source citée. Faux négatif du critère automatique. | correcte |

**Bilan relu : 20/20 réponses exactes et sourcées, dont 2 incomplètes** ; la question hors corpus (dose de fongicide)
est correctement déclinée avec une orientation vers un conseiller, sans aucune dose inventée.

Limites : évaluation sur 20 questions rédigées par l'enseignant, proches du vocabulaire des fiches ; une seule exécution
(le LLM n'est pas strictement déterministe) ; quota gratuit Groq, d'où une pause de 8 s entre les questions.
