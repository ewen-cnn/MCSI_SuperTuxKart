# Guide de Configuration et de Calibration : Détection de Couleur (FIRE)

Ce document explique en détail le fonctionnement et le réglage de chaque paramètre du module de détection d'objets et de cartes colorées ([`classes/colorDetector.py`](classes/colorDetector.py)) utilisé pour lancer les objets (`FIRE` / touche Espace) dans SuperTuxKart.

---

## 1. Principes de Détection : L'Espace Colorimétrique HSV

Contrairement à l'espace RVB (RGB) où la luminosité ambiante altère simultanément le rouge, le vert et le bleu, l'espace **HSV** (Teinte, Saturation, Valeur) sépare la nature chromatique de la couleur de son éclairage :

- **H (Hue / Teinte) [0 - 180 dans OpenCV]** :
  - Représente l'angle sur le cercle des couleurs ($0^\circ$ à $360^\circ$ divisé par 2).
  - *Rouge* : se trouve aux deux extrémités du spectre ($0 - 10$ et $168 - 180$).
  - *Orange* : $10 - 22$.
  - *Jaune* : $20 - 35$.
  - *Vert* : $36 - 86$.
  - *Bleu* : $95 - 135$.
- **S (Saturation) [0 - 255]** :
  - Intensité ou pureté de la couleur.
  - $0$ = nuances de gris/blanc (teintes délavées).
  - $255$ = couleur pure et saturée.
  - **Filtre anti-faux positifs majeur** : les murs beiges, la peau humaine et les vêtements pâles ont généralement une saturation $< 60-80$. Une carte rouge ou un objet vif a une saturation $\ge 100$.
- **V (Value / Luminosité) [0 - 255]** :
  - Intensité lumineuse du pixel.
  - $0$ = obscurité totale (ombres).
  - $255$ = luminosité maximale.

---

## 2. Répertoire Complet des Paramètres

Tous les paramètres sont centralisés dans [`classes/config.py`](classes/config.py) et modifiables directement ou via la ligne de commande.

### A. Sélection de la Couleur et Plages HSV

| Paramètre | Valeur par défaut | Description | Conseil de réglage |
| :--- | :--- | :--- | :--- |
| `COLOR_PRESET` | `"red"` | Couleur cible (`red`, `green`, `blue`, `yellow`, `orange`, `custom`). | Choisissez la couleur de votre carte physique. |
| `COLOR_CUSTOM_LOWER` | `(0, 100, 70)` | Borne HSV inférieure en mode personnalisé. | Augmentez $S$ si de fausses détections apparaissent. |
| `COLOR_CUSTOM_UPPER` | `(10, 255, 255)` | Borne HSV supérieure en mode personnalisé. | Réduisez $H_{\max}$ si la détection déborde sur une couleur voisine. |

### B. Filtres Géométriques (Distinction d'une Carte par rapport à l'Environnement)

Les objets colorés du quotidien (vêtements, lèvres, tasses) peuvent partager la même teinte qu'une carte. Les filtres géométriques éliminent ces éléments parasites :

| Paramètre | Valeur par défaut | Description | Conseil de réglage |
| :--- | :--- | :--- | :--- |
| `COLOR_MIN_AREA` | `300 px` | Superficie minimale du contour en pixels. | **Contre le bruit** : augmentez à $600-1000$ si des reflets ou petits objets au loin déclenchent le tir. Diminuez à $150-200$ si vous tenez la carte loin de la webcam. |
| `COLOR_MAX_AREA` | `45000 px` | Superficie maximale du contour en pixels. | **Contre l'arrière-plan** : évite qu'un t-shirt ou un pan de mur rouge entier ne déclenche le tir. |
| `COLOR_MAX_ASPECT_RATIO` | `3.5` | Ratio $\frac{\max(w,h)}{\min(w,h)}$ du rectangle englobant. | Une carte normale a un ratio d'environ $1.4$ à $1.6$. Ce filtre rejette les formes très allongées (câbles, montants de fenêtres, arêtes de table). |
| `COLOR_MIN_SOLIDITY` | `0.65` | Ratio $\frac{\text{Aire Contour}}{\text{Aire Enveloppe Convexe}}$. | Une carte est un polygone plein et compact ($\text{solidité} \approx 0.90 - 1.0$). Rejette les mains ouvertes, doigts écartés ou formes en U. |
| `COLOR_MIN_EXTENT` | `0.35` | Ratio $\frac{\text{Aire Contour}}{\text{Aire Bounding Box}}$. | Mesure le taux de remplissage du rectangle. Une carte remplit $> 70\%$ de son rectangle englobant. Rejette les objets en diagonale ou creux. |

### C. Filtrage Temporel et Anti-Rebond (Debounce)

| Paramètre | Valeur par défaut | Description | Conseil de réglage |
| :--- | :--- | :--- | :--- |
| `COLOR_CONFIRM_FRAMES` | `2` images | Nombre d'images consécutives où l'objet doit être reconnu avant validation. | Élimine à 100% les artefacts vidéo d'une seule image et les bruits de capteur. Augmentez à $3$ pour un tir ultra-sécurisé. |
| `COLOR_COOLDOWN_SECONDS` | `1.2 s` | Temps d'attente obligatoire entre deux lancers consécutifs. | Empêche de vider tout son stock d'objets en restant devant la caméra. |
| `COLOR_PULSE_DURATION` | `0.20 s` | Durée pendant laquelle l'impulsion OSC `FIRE` reste active. | Assure que SuperTuxKart enregistre bien la pression de la touche Espace. |

---

## 3. Guide de Calibration selon l'Environnement

### Scénario 1 : Éclairage Faible (Soir / Pièce Sombre)
- **Symptôme** : La carte n'est pas détectée ou seulement très près de la caméra.
- **Cause** : La composante de luminosité $V$ chute en dessous de $70$.
- **Action** :
  - Diminuer la borne minimale de luminosité $V_{\min}$ de $70$ à $40-50$.
  - Diminuer légèrement $S_{\min}$ de $100$ à $70-80$.

### Scénario 2 : Lumière Naturelle Vive / Reflets du Soleil
- **Symptôme** : Les reflets blancs sur une carte plastifiée créent des "trous" dans le masque.
- **Cause** : Le reflet spéculaire blanc désature localement la couleur ($S \to 0$).
- **Action** :
  - Réduire l'exposition automatique de la webcam si possible.
  - Utiliser une carte ou un objet mat (papier cartonné mat).
  - Maintenir $S_{\min} \ge 80$ pour éviter de capter le blanc.

### Scénario 3 : Faux Positifs avec la Peau ou des Vêtements
- **Symptôme** : Le visage ou les lèvres déclenchent le tir en mode `red`.
- **Cause** : Les lèvres et joues ont une teinte proche du rouge mais une saturation plus faible que du papier rouge vif.
- **Action** :
  - **Augmenter `S_min`** de $100$ à $130-150$ : seuls les rouges ultra-vifs seront acceptés.
  - **Augmenter `COLOR_MIN_AREA`** à $600$ pour que les lèvres (trop petites) soient ignorées.

---

## 4. Calibration Automatique en Direct (Touche C)

Une fonction de calibration instantanée est intégrée au retour vidéo OpenCV :

1. Lancez le tracking :
   ```bash
   .venv/bin/python SetUp_Collab/face_tracking.py --color red
   ```
2. Placez l'objet ou la carte physique **au centre exact de l'image** de la caméra (à environ 30-50 cm).
3. Appuyez sur la touche **<kbd>C</kbd>** du clavier.
4. L'algorithme échantillonne automatiquement une zone de $80 \times 80$ pixels au centre, calcule les médianes H, S, V de votre objet sous votre éclairage actuel, et calcule les tolérances adaptatives optimales.
5. Le HUD affiche : `Objet calibré ! (H:..., S:..., V:...)`. Le système bascule automatiquement sur ce profil personnalisé.

---

## 5. Exemples de Lignes de Commande

```bash
# 1. Utiliser une carte bleue avec un seuil de surface plus grand
.venv/bin/python SetUp_Collab/STK_collab_input.py --color blue --color-min-area 500

# 2. Utiliser un carton jaune avec un délai de recharge rapide (0.8s)
.venv/bin/python SetUp_Collab/STK_collab_input.py --color yellow --color-cooldown 0.8

# 3. Désactiver complètement la détection de couleur
.venv/bin/python SetUp_Collab/STK_collab_input.py --color off

# 4. Tester visuellement avec OpenCV sans lancer le jeu
.venv/bin/python SetUp_Collab/face_tracking.py --color red
```
