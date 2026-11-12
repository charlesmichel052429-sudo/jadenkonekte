# Évaluation de l'assistant agronome

LLM : `openai/gpt-oss-120b` (Groq) · recherche hybride (vecteurs + plein texte) · seuil de similarité 0.35

**20/20 réponses jugées réussies** par les critères automatiques.

| # | Question | Fiche attendue | Recherche | Citée | Éléments | Durée | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Quand faut-il arroser les tomates dans la journée ? | 01_tomate_culture.md | oui | oui | 2/2 | 2.5 s | **réussi** |
| 2 | Pourquoi mes tomates ont une tache noire sous le fruit ? | 01_tomate_culture.md | oui | oui | 2/3 | 2.5 s | **réussi** |
| 3 | Combien de temps attendre avant de replanter des tomates au même endroit ? | 01_tomate_culture.md | oui | oui | 3/3 | 2.2 s | **réussi** |
| 4 | Comment reconnaître le mildiou sur la tomate ? | 02_tomate_maladies.md | oui | oui | 2/2 | 1.4 s | **réussi** |
| 5 | Quel insecte transmet le virus des feuilles jaunes en cuillère ? | 02_tomate_maladies.md | oui | oui | 2/2 | 1.0 s | **réussi** |
| 6 | Existe-t-il un traitement contre le TYLCV ? | 02_tomate_maladies.md | oui | oui | 2/2 | 4.7 s | **réussi** |
| 7 | Comment éviter la propagation du virus de la mosaïque ? | 02_tomate_maladies.md | oui | oui | 3/3 | 2.1 s | **réussi** |
| 8 | Ma plante de tomate flétrit d'un coup mais les feuilles restent vertes, qu'est-ce que c'est ? | 02_tomate_maladies.md | oui | oui | 2/3 | 1.7 s | **réussi** |
| 9 | Quelles conditions favorisent les acariens ? | 02_tomate_maladies.md | oui | oui | 2/2 | 2.1 s | **réussi** |
| 10 | Quelle est la principale maladie de l'igname aux Antilles ? | 03_igname.md | oui | oui | 2/2 | 1.6 s | **réussi** |
| 11 | Pourquoi planter l'igname sur buttes ? | 03_igname.md | oui | oui | 2/2 | 1.4 s | **réussi** |
| 12 | Quand arrêter d'arroser l'igname ? | 03_igname.md | oui | oui | 2/2 | 2.3 s | **réussi** |
| 13 | Comment planter une christophine ? | 04_christophine.md | oui | oui | 1/2 | 1.5 s | **réussi** |
| 14 | La christophine supporte-t-elle l'eau stagnante ? | 04_christophine.md | oui | oui | 3/3 | 1.2 s | **réussi** |
| 15 | Mon capteur indique 999 % d'humidité, faut-il arrêter l'arrosage ? | 05_irrigation_sol.md | oui | oui | 2/2 | 2.1 s | **réussi** |
| 16 | À partir de quelle humidité du sol faut-il arroser ? | 05_irrigation_sol.md | oui | oui | 3/3 | 2.3 s | **réussi** |
| 17 | Faut-il arroser si une averse est prévue ? | 05_irrigation_sol.md | oui | oui | 1/2 | 15.0 s | **réussi** |
| 18 | Le modèle détecte du mildiou avec un score de 0,55 : que faire ? | 06_protocole_alerte.md | oui | oui | 4/4 | 2.9 s | **réussi** |
| 19 | Quand publier une alerte sur le réseau régional ? | 06_protocole_alerte.md | oui | oui | 1/1 | 13.2 s | **réussi** |
| 20 | Quelle est la dose de fongicide à utiliser contre le mildiou ? | hors corpus | — | — | — | 4.5 s | **réussi** |

## Réponses complètes

### 1. Quand faut-il arroser les tomates dans la journée ?

*Attendu : tôt le matin ou en fin d'après-midi, au pied*  
*Sources transmises : [1] 01_tomate_culture.md › Besoins en eau; [2] 01_tomate_culture.md › Conditions de culture; [3] 01_tomate_culture.md › Implantation; [4] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV)*

> Oui, il faut arroser les tomates tôt le matin ou en fin d’après‑midi pour limiter l’évaporation.  
> - Arroser au pied, de préférence en goutte‑à‑goutte, sans mouiller le feuillage.  
> - Suspendre l’arrosage après une pluie significative.  
> - Un paillage aide à réduire l’évaporation.  
> 
> [1]

### 2. Pourquoi mes tomates ont une tache noire sous le fruit ?

*Attendu : nécrose apicale, arrosage irrégulier, calcium*  
*Sources transmises : [1] 01_tomate_culture.md › Besoins en eau; [2] 02_tomate_maladies.md › Septoriose; [3] 02_tomate_maladies.md › Corynesporiose (tache cible); [4] 02_tomate_maladies.md › Gale bactérienne (tache bactérienne)*

> Oui, il s’agit très probablement d’une nécrose apicale, c’est‑à‑dire d’une tache noire à la base du fruit liée à un déséquilibre calcique.
> 
> - Cette nécrose apparaît quand le fruit subit des à‑coups d’irrigation : le sol passe d’un état très sec à très humide, ce qui perturbe l’alimentation en calcium du fruit et provoque la tache noire à la base [1].  
> - Pour limiter ce problème, il faut maintenir le sol **frais mais jamais détrempé**, arroser régulièrement au pied (de préférence en goutte‑à‑goutte) sans mouiller le feuillage, et privilégier les arrosages tôt le matin ou en fin d’après‑midi afin de réduire l’évaporation [1].  
> - Un paillage (paille, bagasse, feuilles sèches) aide à limiter l’évaporation et les éclaboussures de terre sur les feuilles basses, réduisant ainsi les fluctuations d’humidité du sol [1].  
> - Suspendre l’arrosage après une pluie significative évite également les excès d’humidité [1].

### 3. Combien de temps attendre avant de replanter des tomates au même endroit ?

*Attendu : trois à quatre ans, rotation, solanacées*  
*Sources transmises : [1] 01_tomate_culture.md › Implantation; [2] 01_tomate_culture.md › Surveillance; [3] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV); [4] 02_tomate_maladies.md › Acariens (tétranyque tisserand)*

> Oui, il faut attendre trois à quatre ans avant de replanter des tomates (ou d’autres solanacées) au même endroit.  
> - Pratique recommandée : rotation des cultures, ne pas replanter de tomate, aubergine, piment ou poivron au même emplacement pendant trois ou quatre ans [1]

### 4. Comment reconnaître le mildiou sur la tomate ?

*Attendu : taches huileuses brun-vert, duvet blanc au revers*  
*Sources transmises : [1] 01_tomate_culture.md › Surveillance; [2] 01_tomate_culture.md › Besoins en eau; [3] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV); [4] 02_tomate_maladies.md › Mildiou*

> Oui, le mildiou se reconnaît à des symptômes bien précis sur la tomate.
> 
> - **Symptômes visibles** : grandes taches brun‑vert d’aspect huileux sur les feuilles, présence d’un duvet blanchâtre au revers des feuilles par temps humide, ainsi que brunissement des tiges et des fruits [4].
> - **Conditions favorables** : humidité élevée, feuillage mouillé longtemps et températures modérées favorisent l’apparition et la propagation rapide du mildiou [4].
> - **Prévention / actions** : aérer la culture, éviter de mouiller le feuillage et éliminer rapidement les plants atteints [4].

### 5. Quel insecte transmet le virus des feuilles jaunes en cuillère ?

*Attendu : aleurode, Bemisia tabaci*  
*Sources transmises : [1] 02_tomate_maladies.md › Virus des feuilles jaunes en cuillère (TYLCV); [2] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV); [3] 01_tomate_culture.md › Surveillance; [4] 03_igname.md › Anthracnose*

> Oui, le virus des feuilles jaunes en cuillère (TYLCV) est transmis par l’aleurode, communément appelée mouche blanche (*Bemisia tabaci*)[1].

### 6. Existe-t-il un traitement contre le TYLCV ?

*Attendu : pas de traitement curatif ; prévention*  
*Sources transmises : [1] 02_tomate_maladies.md › Virus des feuilles jaunes en cuillère (TYLCV); [2] 02_tomate_maladies.md › Présentation de la fiche*

> Non, il n'existe pas de traitement curatif contre le virus des feuilles jaunes en cuillère (TYLCV) ; la lutte se fait par prévention (variétés tolérantes, filets anti‑insectes, désherbage, arrachage des plants atteints)[1].  
> 
> Cette fiche est pédagogique et ne remplace pas l’avis d’un technicien agricole ; pour toute décision de traitement, consultez un conseiller agricole[2].

### 7. Comment éviter la propagation du virus de la mosaïque ?

*Attendu : mains, outils désinfectés, éliminer les plants*  
*Sources transmises : [1] 06_protocole_alerte.md › 2. Limiter la propagation sur l'exploitation; [2] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV); [3] 02_tomate_maladies.md › Virus des feuilles jaunes en cuillère (TYLCV); [4] 06_protocole_alerte.md › 3. Prévenir le voisinage*

> Oui, il faut empêcher la transmission du virus.
> 
> - Retirer et évacuer immédiatement les plants ou feuilles atteints, sans les laisser au sol ni les composter.  
> - Désinfecter soigneusement les outils et se laver les mains après chaque manipulation.  
> - Éviter l’arrosage par aspersion et ne pas circuler dans la parcelle mouillée afin de limiter les contacts.  
> - Le virus se transmet surtout par contact (mains, outils, semences) et est très résistant dans l’environnement, d’où l’importance de la désinfection et de l’élimination des plants infectés.  
> 
> [2] : symptômes, transmission par contact et prévention par lavage des mains, désinfection des outils et élimination des plants atteints.  
> [1] : mesures concrètes pour limiter la propagation sur l’exploitation (retrait, désinfection, suspension de l’arrosage par aspersion).

### 8. Ma plante de tomate flétrit d'un coup mais les feuilles restent vertes, qu'est-ce que c'est ?

*Attendu : flétrissement bactérien, Ralstonia, non détecté par le modèle*  
*Sources transmises : [1] 02_tomate_maladies.md › Virus de la mosaïque de la tomate (ToMV); [2] 02_tomate_maladies.md › Flétrissement bactérien (à connaître, non détecté par le modèle); [3] 01_tomate_culture.md › Implantation; [4] 01_tomate_culture.md › Surveillance*

> Oui, il s’agit très probablement d’un flétrissement bactérien.
> 
> - **Symptômes** : flétrissement brutal de la plante alors que les feuilles restent vertes ; un exsudat laiteux apparaît lorsqu’on coupe la tige et la plonge dans l’eau[2].  
> - **Agent responsable** : bactérie du sol *Ralstonia solanacearum*[2].  
> - **Contexte** : maladie majeure de la tomate en zone tropicale[2].  
> - **Prévention** : choisir des variétés ou porte‑greffes tolérants, pratiquer une rotation longue (au moins 3‑4 ans) et éviter de replanter sur des sols où la maladie a déjà été observée[2].  
> 
> Le modèle ne détecte pas automatiquement ce problème, il faut donc confirmer avec un diagnostic visuel ou un conseiller agronome.

### 9. Quelles conditions favorisent les acariens ?

*Attendu : temps chaud et sec, stress hydrique*  
*Sources transmises : [1] 02_tomate_maladies.md › Acariens (tétranyque tisserand); [2] 03_igname.md › Récolte et conservation; [3] 04_christophine.md › Problèmes courants; [4] 01_tomate_culture.md › Conditions de culture*

> Oui, les acariens (tétranyque tisserand) sont favorisés par des conditions de temps chaud et sec, ainsi que par le stress hydrique des plantes.  
> - Conditions favorables : temps chaud et sec, plantes stressées par le manque d’eau [1]  
> - Prévention : éviter le stress hydrique et surveiller le revers des feuilles [1]

### 10. Quelle est la principale maladie de l'igname aux Antilles ?

*Attendu : anthracnose, Colletotrichum gloeosporioides*  
*Sources transmises : [1] 03_igname.md › Anthracnose; [2] 03_igname.md › Généralités; [3] 02_tomate_maladies.md › Flétrissement bactérien (à connaître, non détecté par le modèle); [4] 06_protocole_alerte.md › 4. Signaler si nécessaire*

> Oui, la principale maladie de l'igname aux Antilles est l’anthracnose.  
> - Causée par le champignon *Colletotrichum gloeosporioides* ; favorisée par la pluie et l’humidité [1].  
> - Symptômes : petites taches brunes à noires sur les feuilles qui s’agrandissent et fusionnent, dessèchement des feuilles et des tiges (« brûlure ») [1].  
> - Prévention : utiliser des semences saines, choisir des variétés tolérantes, assurer un espacement suffisant et éliminer les résidus de culture [1].

### 11. Pourquoi planter l'igname sur buttes ?

*Attendu : éviter l'excès d'eau, pourriture des tubercules*  
*Sources transmises : [1] 03_igname.md › Plantation; [2] 04_christophine.md › Plantation; [3] 03_igname.md › Récolte et conservation; [4] 03_igname.md › Généralités*

> Oui, on plante l’igname sur buttes pour éviter l’excès d’eau au niveau des tubercules, ce qui prévient les risques de pourriture.  
> - Cause : l’excès d’eau autour des tubercules peut les endommager.  
> - Condition favorable : planter sur buttes ou billons.  
> - Précaution : choisir des fragments sains et planter en début de saison des pluies.  
> [1]

### 12. Quand arrêter d'arroser l'igname ?

*Attendu : fin de cycle, feuillage jaunit*  
*Sources transmises : [1] 03_igname.md › Besoins en eau; [2] 05_irrigation_sol.md › Seuils indicatifs pour le projet*

> Oui, il faut arrêter d’arroser l’igname en fin de cycle, lorsque le feuillage jaunit naturellement ; à ce stade, il faut réduire puis cesser l’arrosage [1].  
> 
> De plus, si le sol est très humide (humidité > 45 %) il ne faut pas arroser [2].

### 13. Comment planter une christophine ?

*Attendu : fruit germé à moitié enterré, treille*  
*Sources transmises : [1] 03_igname.md › Plantation; [2] 04_christophine.md › Plantation; [3] 04_christophine.md › Généralités; [4] 03_igname.md › Récolte et conservation*

> Oui, on plante la christophine en entier, germé, à moitié enterré, la pointe vers le haut.  
> - Prévoir une treille ou une tonnelle solide car la plante est vigoureuse et grimpe.  
> - Elle préfère les zones fraîches et humides, plus favorables en altitude, et un sol riche en matière organique.  
> 
> [2]

### 14. La christophine supporte-t-elle l'eau stagnante ?

*Attendu : non, pourriture du collet, sol drainé*  
*Sources transmises : [1] 04_christophine.md › Besoins en eau; [2] 03_igname.md › Besoins en eau; [3] 01_tomate_culture.md › Besoins en eau; [4] 03_igname.md › Plantation*

> Non, la christophine ne supporte pas l'eau stagnante ; elle peut faire pourrir le collet.  
> - Elle demande beaucoup d'eau pendant la croissance et la fructification, mais nécessite un sol bien drainé ; l'eau stagnante provoque la pourriture du collet [1].

### 15. Mon capteur indique 999 % d'humidité, faut-il arrêter l'arrosage ?

*Attendu : valeur aberrante, panne du capteur*  
*Sources transmises : [1] 05_irrigation_sol.md › Seuils indicatifs pour le projet; [2] 05_irrigation_sol.md › Bonnes pratiques d'arrosage; [3] 05_irrigation_sol.md › Exemple de règle automatique; [4] 05_irrigation_sol.md › Saisons*

> Oui, il faut arrêter l’arrosage et vérifier le capteur.  
> 
> - Une valeur négative, nulle ou supérieure à 100 % signale une panne du capteur, pas un sol sec ; il faut donc suspendre l’irrigation et contrôler le dispositif [2].  
> - Le système de règle automatique ne s’applique qu’aux valeurs réelles d’humidité du sol ; une valeur aberrante doit être traitée comme une erreur de mesure [3].  
> 
> En cas de doute, contactez un conseiller ou un technicien agricole pour vérifier le capteur.

### 16. À partir de quelle humidité du sol faut-il arroser ?

*Attendu : 20-30 % si pas de pluie prévue, < 20 % rapidement ; seuils indicatifs*  
*Sources transmises : [1] 05_irrigation_sol.md › Seuils indicatifs pour le projet; [2] 05_irrigation_sol.md › Comprendre la mesure; [3] 05_irrigation_sol.md › Exemple de règle automatique; [4] 05_irrigation_sol.md › Bonnes pratiques d'arrosage*

> Oui, il faut arroser lorsque l’humidité du sol descend en dessous de 30 % :
> 
> - **20 % – 30 %** : début de dessèchement ; arroser si aucune pluie n’est prévue.  
> - **< 20 %** : sol sec, stress probable ; arroser rapidement.  
> 
> Ces seuils proviennent du tableau des seuils indicatifs [1].  
> 
> **Précisions complémentaires**  
> - La mesure porte sur l’**humidité volumique** du sol (part du volume occupée par l’eau) [2].  
> - La règle automatique peut être affinée avec la prévision de pluie et l’heure de la journée [3].  
> - Bonnes pratiques : arroser tôt le matin ou en fin d’après‑midi, en plusieurs apports modérés, et éviter d’arroser si une pluie significative est attendue [4].

### 17. Faut-il arroser si une averse est prévue ?

*Attendu : non, tenir compte de la météo*  
*Sources transmises : [1] 05_irrigation_sol.md › Bonnes pratiques d'arrosage; [2] 05_irrigation_sol.md › Seuils indicatifs pour le projet; [3] 05_irrigation_sol.md › Exemple de règle automatique; [4] 05_irrigation_sol.md › Saisons*

> Non, il ne faut pas arroser si une averse est prévue.  
> - L’extrait indique de **ne pas arroser si une pluie significative est prévue dans les prochaines heures** : c’est l’intérêt d’une API météo[1].  
> - La règle automatique montre que le **cumul de pluie prévu sur 6 h** doit être inférieur à 2 mm pour déclencher l’arrosage[3].  
> 
> Ainsi, en présence d’une averse prévue, l’arrosage doit être suspendu.

### 18. Le modèle détecte du mildiou avec un score de 0,55 : que faire ?

*Attendu : score < 0,7 : reprendre des photos, comparer, technicien*  
*Sources transmises : [1] 06_protocole_alerte.md › 1. Confirmer le diagnostic; [2] 06_protocole_alerte.md › Présentation de la fiche; [3] 02_tomate_maladies.md › Flétrissement bactérien (à connaître, non détecté par le modèle); [4] 05_irrigation_sol.md › Présentation de la fiche*

> Oui, le score de confiance est trop faible ; il faut reprendre des photos.
> 
> - Vérifier le score : comme il est en dessous de 0,7, refaire une ou plusieurs photos (feuille entière, bien éclairée, fond neutre) [1].
> - Comparer les nouvelles images avec la description des symptômes du mildiou dans la fiche « Tomate — maladies et ravageurs » [1].
> - En cas de doute persistant, solliciter l’avis d’un technicien agricole [1].

### 19. Quand publier une alerte sur le réseau régional ?

*Attendu : après confirmation par l'exploitant*  
*Sources transmises : [1] 06_protocole_alerte.md › 3. Prévenir le voisinage*

> Oui, une alerte ne doit être publiée sur le réseau régional qu’après **confirmation** par l’exploitant de la maladie détectée[1].

### 20. Quelle est la dose de fongicide à utiliser contre le mildiou ?

*Attendu : hors du corpus : l'assistant doit refuser de donner une dose et orienter vers un conseiller*  
*Sources transmises : [1] 02_tomate_maladies.md › Présentation de la fiche; [2] 02_tomate_maladies.md › Mildiou*

> Je ne trouve pas cette information dans les fiches techniques.  
> Je vous conseille de contacter un conseiller agricole ou un technicien pour obtenir la dose appropriée de fongicide.


## Remarques (2026-11-11)

Une première exécution de cette version donnait 15/20 aux critères automatiques et une réponse fausse (question 2).
Trois corrections ont été apportées, puis l'évaluation a été relancée en entier :

1. **Embeddings** : la version quantifiée du modèle classait mal les passages ; le modèle complet est utilisé, avec
   la longueur de séquence pour laquelle il a été entraîné (128 tokens au lieu de 256).
2. **Consigne du LLM** : répondre d'abord directement, puis reprendre les précisions utiles de l'extrait (cause,
   agent responsable, précautions, limites du diagnostic automatique).
3. **Critère automatique** : les mots de trois lettres (« non », « sol ») n'étaient jamais reconnus ; ils sont
   maintenant recherchés en mot entier.

Limites : 20 questions proches du vocabulaire des fiches ; une seule exécution (le LLM n'est pas strictement
déterministe, le score peut varier d'une exécution à l'autre) ; les critères automatiques cherchent des mots-clés
et ne remplacent pas une relecture ; quota gratuit Groq, d'où une pause de 8 s entre les questions.
