# SuperTuxKart — Face Tracking Controller (Solo & Collaborative)

Contrôleur de jeu interactif pour **SuperTuxKart** basé sur la vision par ordinateur (**MediaPipe Face Tracking**), la détection d'objets colorés et des capteurs physiques embarqués (**Arduino**).

Le système permet de piloter un kart en **Solo** (un seul joueur gère tout avec le visage) ou en **Duo Collaboratif** (deux joueurs se partagent le contrôle : l'un tourne, l'autre accélère/freine).

---

Projet réalisé en binôme dans le module MCSI (Master SIIA, ENIB).

## Architecture

```text
 Webcam ──► face_tracking / colorDetector (MediaPipe, OpenCV) ─┐
                                                              ├─► KartState ─► actions ─► UDP :6006 ─► STK_input_server ─► touches clavier ─► SuperTuxKart
 Arduino (EMG A0, vibration D2, IMU) ──► port série ──────────┘
```

- **Fusion multimodale** : chaque source (visage, couleur, capteurs) met à jour un état commun du kart (`classes/KartState.py`) ; les actions sont ensuite traduites en appuis/relâchements de touches.
- **Découplage par UDP** : la détection et l'injection clavier tournent dans deux processus séparés. Seul le serveur d'injection a besoin des droits root (module `keyboard` sous Linux).
- **Calibrage à chaud** : position neutre de la tête, distance de référence et couleur de la carte se recalibrent pendant la partie.

Le dépôt contient deux dispositifs :

| Dossier | Entrées | Usage |
| --- | --- | --- |
| `SetUp_Collab/` | Webcam (visage + objet coloré) et capteurs Arduino | Contrôle solo ou à deux joueurs, décrit ci-dessous |
| `SetUp_Performance/` | Smartphone via l'application MultiSense (pad tactile + accéléromètre, protocole OSC sur le port 8000) | Pilotage par inclinaison du téléphone |

## Résumé des Contrôles

| Action dans STK | Touche Clavier | Source de Contrôle |
| :--- | :--- | :--- |
| **Direction Gauche / Droite** | <kbd>←</kbd> / <kbd>→</kbd> | **Caméra (Visage P1 / Solo)** : Inclinaison de la tête (`--steering face`) ou Position horizontale (`--steering position`) |
| **Accélération** | <kbd>↑</kbd> | **Caméra (Profondeur $Z$ P2 / Solo)** : Se rapprocher de la webcam |
| **Frein / Marche Arrière** | <kbd>↓</kbd> | **Caméra (Profondeur $Z$ P2 / Solo)** : S'éloigner / reculer de la webcam |
| **Tir d'Objet (`FIRE`)** | <kbd>Espace</kbd> | **Caméra (Objet coloré)** : Présenter une carte/objet vert(e) ou rouge devant la caméra |
| **Dérapage (`Drift`)** | <kbd>V</kbd> | **Capteur Musculaire EMG (Arduino A0)** : Contraction musculaire (toggle ON/OFF) |
| **Nitro** | <kbd>N</kbd> | **Capteur de Vibration (Arduino Pin 2)** : Coup / secousse sur le capteur |
| **Sauvetage (`Rescue`)** | <kbd>Retour arrière</kbd> | **Gyroscope / Accéléromètre** : Secousse physique rapide de la carte |

---

## Démarrage Rapide

### Prérequis

Linux, Python 3.10 à 3.12 (versions supportées par MediaPipe), une webcam et [SuperTuxKart](https://supertuxkart.net/) (testé avec la version 1.2). La carte Arduino est optionnelle : sans elle, les commandes caméra fonctionnent seules.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Le croquis Arduino est dans `SetUp_Collab/main/main.ino`. La carte est détectée automatiquement au lancement grâce à son identifiant USB Arduino (VID `0x2341`).

### Méthode 1 : Lancement Tout-en-Un (Recommandé)

1. **Terminal 1 — Lancer le jeu et le serveur d'entrées :**
   ```bash
   STK_RUN=~/SuperTuxKart-1.2-linux/run_game.sh ./launch_game.sh
   ```
   *(Entrez votre mot de passe `sudo` si demandé, nécessaire pour l'injection des touches sous Linux).*

2. **Terminal 2 — Lancer le contrôleur de visage :**

   - **Mode Duo Collaboratif (2 Joueurs) :**
     ```bash
     .venv/bin/python SetUp_Collab/STK_collab_input.py --mode duo --steering position --color green
     ```

   - **Mode Solo (1 Joueur) :**
     ```bash
     .venv/bin/python SetUp_Collab/STK_collab_input.py --mode solo --steering position --color green
     ```

---

### Méthode 2 : Lancement Manuel Composant par Composant

Si vous préférez lancer chaque élément séparément :

```bash
# Terminal 1 : Serveur de frappe de touches (UDP 6006)
sudo .venv/bin/python SetUp_Collab/STK_input_server.py

# Terminal 2 : SuperTuxKart
"$STK_RUN"   # chemin vers SuperTuxKart, par ex. ~/SuperTuxKart-1.2-linux/run_game.sh

# Terminal 3 : Contrôleur de tracking collaboratif
.venv/bin/python SetUp_Collab/STK_collab_input.py --mode duo --steering position --color green
```

---

## Modes de Jeu

### 1. Mode Duo Collaboratif (`--mode duo`)
Deux joueurs se tiennent côte à côte devant la webcam :
- **Joueur 1 (Visage à Gauche sur l'écran miroir)** : Contrôle la **Direction**.
- **Joueur 2 (Visage à Droite sur l'écran miroir)** : Contrôle la **Vitesse** (Accélération / Freinage).
- **Les deux joueurs** peuvent présenter une carte colorée pour tirer des objets.

### 2. Mode Solo (`--mode solo`)
Un seul joueur contrôle la totalité du kart :
- Direction avec la tête.
- Accélération / freinage en s'approchant ou s'éloignant de la webcam.
- Tir d'objets avec la carte colorée.
L'objectif de ce mode est de pouvoir tester l'entièreté du code en étant seul.   

### 3. Mode Automatique (`--mode auto`, défaut)
Bascule automatiquement en **Duo** lorsque 2 visages sont détectés, et repasse en **Solo** si une seule personne est présente.

---

## Options de Direction (`--steering`)

Le script supporte deux modes de direction selon vos préférences :

1. **Mode Position Horizontale (`--steering position`) :**
   - Décalez la tête latéralement à gauche ou à droite au-delà des repères visuels affichés à l'écran.
   - Les repères changent dynamiquement de couleur (cyan au repos, vert vif en braquage).
   - Plus vous dépassez la ligne, plus le braquage est intense (modulation PWM).

2. **Mode Inclinaison de la Tête (`--steering face`, défaut) :**
   - Penchez la tête vers la droite ou la gauche.
   - L'angle est mesuré entre les deux yeux.
   - Calibrage automatique de la position neutre pendant les 2 premières secondes.

---

## Détection d'Objets Colorés & Tir (`--color`)

Pour tirer des objets en jeu (`FIRE`) sans appuyer sur le clavier, présentez un objet ou un carton de couleur devant la webcam :

- **Couleurs prédéfinies :** `--color green` (défaut), `--color red`, `--color blue`, `--color yellow`, `--color orange`.
- **Désactiver :** `--color off`.
- **Réticule & Calibrage instantané (<kbd>C</kbd>) :**
  Un réticule central `[ CALIB (C) ]` apparaît à l'écran. Placez votre objet au centre et appuyez sur <kbd>C</kbd>. Une protection anti-teint rejette automatiquement la peau et les lèvres pour éviter tout faux positif !
- **Réinitialiser (<kbd>R</kbd>) :**
  Appuyez sur <kbd>R</kbd> pour revenir instantanément au préréglage initial de couleur.
- **Tir unitaire avec délai de recharge :**
  La détection génère une impulsion unique par apparition d'objet avec un cooldown de 1.4s. Si vous possédez 3 objets en jeu, vous pouvez désormais les déclencher un par un de manière contrôlée sans les vider tous d'un coup.

---

## Calibrage de la Distance Neutre (<kbd>Z</kbd>)

Le joueur responsable de la vitesse (accélération / freinage) dispose d'un calibrage dynamique :
- **Calibrage automatique :** Pendant les 2,5 premières secondes au lancement, la distance moyenne de repos est enregistrée comme référence ($Z$ neutre).
- **Calibrage à la volée (<kbd>Z</kbd>) :** À tout moment, mettez-vous en position assise confortable et appuyez sur <kbd>Z</kbd> pour définir cette distance comme point zéro.
- Avancez de $+7\text{ cm}$ par rapport au neutre pour accélérer, reculez de $+7\text{ cm}$ pour freiner, ou restez dans la zone neutre pour la roue libre (*coast*).

---

## Tester Uniquement la Caméra (Sans le Jeu)

Pour vérifier votre cadrage, le flux miroir, la détection des visages et calibrer votre carte de couleur sans lancer SuperTuxKart :

```bash
.venv/bin/python SetUp_Collab/face_tracking.py --steering position --color green
```
- <kbd>Z</kbd> : Calibrer la position neutre de distance (accélération/freinage).
- <kbd>C</kbd> : Échantillonner la couleur dans le réticule central.
- <kbd>R</kbd> : Réinitialiser la couleur par défaut.
- <kbd>ESC</kbd> ou <kbd>Q</kbd> : Quitter.

---

## Licence

[MIT](LICENSE)
