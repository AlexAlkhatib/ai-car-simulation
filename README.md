---
# 🚗 Simulation de voitures autonomes avec NEAT

## 🧩 Installation des dépendances

### 1. Python et pip

Assurez-vous que **Python** est installé sur votre système.
Vous pouvez vérifier en exécutant la commande suivante dans votre terminal :

```bash
python --version
```

Si ce n’est pas le cas, téléchargez et installez Python depuis [python.org](https://www.python.org/).

---

### 2. Installer les dépendances

Ce projet utilise les bibliothèques **pygame** et **neat-python**.
Vous pouvez les installer en exécutant :

```bash
pip install pygame neat-python
```

---

## ⚙️ Lancer le projet

### 1. Configurer le fichier de configuration NEAT

Créez un fichier nommé `config.txt` dans le même répertoire que votre script avec le contenu suivant (ou modifiez les paramètres selon vos besoins) :

```ini
[NEAT]
fitness_criterion     = max
fitness_threshold     = 10000.0
pop_size              = 50
reset_on_extinction   = False

[DefaultGenome]
# node activation options
activation_default      = tanh
activation_mutate_rate  = 0.0
activation_options      = tanh

# node aggregation options
aggregation_default     = sum
aggregation_mutate_rate = 0.0
aggregation_options     = sum

# node bias options
bias_init_mean          = 0.0
bias_init_stdev         = 1.0
bias_max_value          = 30.0
bias_min_value          = -30.0
bias_mutate_power       = 0.5
bias_mutate_rate        = 0.7
bias_replace_rate       = 0.1

# genome compatibility options
compatibility_disjoint_coefficient = 1.0
compatibility_weight_coefficient   = 0.5

# connection add/remove rates
conn_add_prob           = 0.5
conn_delete_prob        = 0.5

# connection enable options
enabled_default         = True
enabled_mutate_rate     = 0.01

# connection weight options
weight_init_mean        = 0.0
weight_init_stdev       = 1.0
weight_max_value        = 30
weight_min_value        = -30
weight_mutate_power     = 0.5
weight_mutate_rate      = 0.8
weight_replace_rate     = 0.1

[DefaultSpeciesSet]
compatibility_threshold = 3.0

[DefaultStagnation]
species_fitness_func = max
max_stagnation       = 20
species_elitism      = 2

[DefaultReproduction]
elitism            = 2
survival_threshold = 0.2
```

---

### 2. Lancer le script principal

Exécutez simplement le script principal dans votre terminal :

```bash
python main.py
```

---

## 🔧 Modifier les paramètres essentiels

### 1. Nombre de voitures générées et de générations

**Fichier `config.txt` :**

```ini
# Modifiez le nombre de voitures (pop_size)
pop_size = 50  # Par exemple
```

**Script principal (`main.py`) :**

```python
# Modifiez le nombre de générations
population.run(run_simulation, 1000)  # Changez 1000 pour le nombre de générations souhaité
```

---

### 2. Changer la carte (map)

**Dans le code :**

```python
# Remplacez 'map.png' par le nom de votre nouvelle carte
game_map = pygame.image.load('map.png').convert()
```

**Par exemple :**

```python
game_map = pygame.image.load('new_map.png').convert()
```

---

### 3. Changer le nombre de neurones

Modifiez les sections `[DefaultGenome]` dans le fichier `config.txt` pour ajuster les paramètres des neurones :

```ini
[DefaultGenome]
num_inputs               = 5   # Nombre d'entrées (capteurs)
num_outputs              = 4   # Nombre de sorties (actions : gauche, droite, accélérer, ralentir)
num_hidden               = 5   # Nombre de neurones cachés
initial_connection       = full
```

---

## 🧪 Exemple de modification des paramètres

Supposons que vous souhaitez :

* Générer **100 voitures**
* Exécuter la simulation pour **500 générations**
* Utiliser une carte différente nommée **new_map.png**
* Avoir **10 neurones cachés**

---

### 1. Dans le fichier `config.txt` :

```ini
pop_size = 100

[DefaultGenome]
num_hidden = 10
```

---

### 2. Dans le script principal (`main.py`) :

```python
# Changez la carte
game_map = pygame.image.load('new_map.png').convert()

# Changez le nombre de générations
population.run(run_simulation, 500)
```

---

## ▶️ Exécuter la simulation

Après avoir apporté toutes les modifications nécessaires, lancez de nouveau le script principal pour exécuter la simulation avec les nouveaux paramètres :

```bash
python main.py
```

---

## 💬 Notes importantes

* Vous pouvez ajuster **la vitesse d’apprentissage**, **la taille de la population** et **la complexité du réseau** directement dans `config.txt`.
* Plus la population et le nombre de générations sont élevés, plus la simulation demandera de ressources.
* Les cartes (`map.png`, `new_map.png`, etc.) doivent être au format **PNG** et contenir une bordure blanche `(255, 255, 255, 255)` pour que les collisions soient détectées correctement.
* Les voitures utilisent 5 radars virtuels (capteurs) et apprennent via un système de **récompense** basé sur la distance parcourue sans collision.

---

## 🧠 En résumé

| Élément               | Fichier concerné | Exemple                                             |
| --------------------- | ---------------- | --------------------------------------------------- |
| Nombre de voitures    | `config.txt`     | `pop_size = 50`                                     |
| Nombre de générations | `main.py`        | `population.run(run_simulation, 1000)`              |
| Carte utilisée        | `main.py`        | `game_map = pygame.image.load('map.png').convert()` |
| Neurones cachés       | `config.txt`     | `num_hidden = 5`                                    |

---

💡 **Astuce :**
Pour suivre la progression des générations et voir combien de voitures sont encore en vie, des informations s’affichent directement à l’écran pendant la simulation :

* `Génération : X`
* `Toujours en vie : Y`

---

🎯 **Commande finale à exécuter :**

```bash
python main.py
```

Et observez vos voitures évoluer génération après génération 🚗💨
Une démonstration parfaite de **l’apprentissage évolutif** appliqué à la conduite autonome.

---
