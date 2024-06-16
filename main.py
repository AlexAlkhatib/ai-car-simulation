
import math
import random
import sys
import os

import neat
import pygame

# Constantes
# WIDTH = 1600
# HEIGHT = 880

WIDTH = 1920
HEIGHT = 1080

CAR_SIZE_X = 60    
CAR_SIZE_Y = 60

BORDER_COLOR = (255, 255, 255, 255) # Couleur pour un crash en cas de collision

current_generation = 0 # Compteur de génération

class Car:

    def __init__(self):
        
        # Charger le sprite de la voiture et le faire pivoter
        self.sprite = pygame.image.load('car.png').convert() # Convertir accélère considérablement
        self.sprite = pygame.transform.scale(self.sprite, (CAR_SIZE_X, CAR_SIZE_Y))
        self.rotated_sprite = self.sprite 

        # self.position = [690, 740] # Position de départ
        self.position = [830, 920] # Position de départ
        self.angle = 0
        self.speed = 0

        self.speed_set = False # Drapeau pour la vitesse par défaut plus tard

        self.center = [self.position[0] + CAR_SIZE_X / 2, self.position[1] + CAR_SIZE_Y / 2] # Calculer le centre

        self.radars = [] # Liste pour les capteurs / radars
        self.drawing_radars = [] # Radars à dessiner

        self.alive = True # Booléen pour vérifier si la voiture est écrasée

        self.distance = 0 # Distance parcourue
        self.time = 0 # Temps écoulé

    def draw(self, screen):
        screen.blit(self.rotated_sprite, self.position) # Dessiner le sprite
        self.draw_radar(screen) # OPTIONNEL POUR LES CAPTEURS

    def draw_radar(self, screen):
        # Optionnellement dessiner tous les capteurs / radars
        for radar in self.radars:
            position = radar[0]
            pygame.draw.line(screen, (0, 255, 0), self.center, position, 1)
            pygame.draw.circle(screen, (0, 255, 0), position, 5)

    def check_collision(self, game_map):
        self.alive = True
        for point in self.corners:
            # Si un coin touche la couleur de la bordure -> crash
            # Suppose un rectangle
            if game_map.get_at((int(point[0]), int(point[1]))) == BORDER_COLOR:
                self.alive = False
                break

    def check_radar(self, degree, game_map):
        length = 0
        x = int(self.center[0] + math.cos(math.radians(360 - (self.angle + degree))) * length)
        y = int(self.center[1] + math.sin(math.radians(360 - (self.angle + degree))) * length)

        # Tant qu'on ne touche pas BORDER_COLOR et que length < 300 (juste un max) -> continuer
        while not game_map.get_at((x, y)) == BORDER_COLOR and length < 300:
            length = length + 1
            x = int(self.center[0] + math.cos(math.radians(360 - (self.angle + degree))) * length)
            y = int(self.center[1] + math.sin(math.radians(360 - (self.angle + degree))) * length)

        # Calculer la distance à la bordure et l'ajouter à la liste des radars
        dist = int(math.sqrt(math.pow(x - self.center[0], 2) + math.pow(y - self.center[1], 2)))
        self.radars.append([(x, y), dist])
    
    def update(self, game_map):
        # Régler la vitesse à 20 pour la première fois
        # Seulement lorsqu'il y a 4 nœuds de sortie avec accélération et décélération
        if not self.speed_set:
            self.speed = 20
            self.speed_set = True

        # Obtenir le sprite pivoté et déplacer dans la bonne direction X
        # Ne pas laisser la voiture s'approcher à moins de 20px du bord
        self.rotated_sprite = self.rotate_center(self.sprite, self.angle)
        self.position[0] += math.cos(math.radians(360 - self.angle)) * self.speed
        self.position[0] = max(self.position[0], 20)
        self.position[0] = min(self.position[0], WIDTH - 120)

        # Augmenter la distance et le temps
        self.distance += self.speed
        self.time += 1
        
        # Même chose pour la position Y
        self.position[1] += math.sin(math.radians(360 - self.angle)) * self.speed
        self.position[1] = max(self.position[1], 20)
        self.position[1] = min(self.position[1], WIDTH - 120)

        # Calculer le nouveau centre
        self.center = [int(self.position[0]) + CAR_SIZE_X / 2, int(self.position[1]) + CAR_SIZE_Y / 2]

        # Calculer les quatre coins
        # La longueur est la moitié du côté
        length = 0.5 * CAR_SIZE_X
        left_top = [self.center[0] + math.cos(math.radians(360 - (self.angle + 30))) * length, self.center[1] + math.sin(math.radians(360 - (self.angle + 30))) * length]
        right_top = [self.center[0] + math.cos(math.radians(360 - (self.angle + 150))) * length, self.center[1] + math.sin(math.radians(360 - (self.angle + 150))) * length]
        left_bottom = [self.center[0] + math.cos(math.radians(360 - (self.angle + 210))) * length, self.center[1] + math.sin(math.radians(360 - (self.angle + 210))) * length]
        right_bottom = [self.center[0] + math.cos(math.radians(360 - (self.angle + 330))) * length, self.center[1] + math.sin(math.radians(360 - (self.angle + 330))) * length]
        self.corners = [left_top, right_top, left_bottom, right_bottom]

        # Vérifier les collisions et effacer les radars
        self.check_collision(game_map)
        self.radars.clear()

        # De -90 à 120 avec un pas de 45, vérifier le radar
        for d in range(-90, 120, 45):
            self.check_radar(d, game_map)

    def get_data(self):
        # Obtenir les distances jusqu'à la bordure
        radars = self.radars
        return_values = [0, 0, 0, 0, 0]
        for i, radar in enumerate(radars):
            return_values[i] = int(radar[1] / 30)

        return return_values

    def is_alive(self):
        # Fonction basique pour vérifier si la voiture est en vie
        return self.alive

    def get_reward(self):
        # Calculer la récompense (peut-être changer ?)
        # return self.distance / 50.0
        return self.distance / (CAR_SIZE_X / 2)

    def rotate_center(self, image, angle):
        # Pivoter le rectangle
        rectangle = image.get_rect()
        rotated_image = pygame.transform.rotate(image, angle)
        rotated_rectangle = rectangle.copy()
        rotated_rectangle.center = rotated_image.get_rect().center
        rotated_image = rotated_image.subsurface(rotated_rectangle).copy()
        return rotated_image


def run_simulation(genomes, config):
    
    # Collections vides pour les réseaux et les voitures
    nets = []
    cars = []

    # Initialiser PyGame et l'affichage
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    # Pour tous les génomes passés, créer un nouveau réseau neuronal
    for i, g in genomes:
        net = neat.nn.FeedForwardNetwork.create(g, config)
        nets.append(net)
        g.fitness = 0

        cars.append(Car())

    # Paramètres de l'horloge
    # Paramètres de police et chargement de la carte
    clock = pygame.time.Clock()
    generation_font = pygame.font.SysFont("Arial", 30)
    alive_font = pygame.font.SysFont("Arial", 20)
    game_map = pygame.image.load('map.png').convert() # Convertir accélère considérablement

    global current_generation
    current_generation += 1

    # Simple compteur pour limiter grossièrement le temps (pas une bonne pratique)
    counter = 0

    while True:
        # Sortir en cas d'événement de quitter
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit(0)

        # Pour chaque voiture, obtenir l'action à entreprendre
        for i, car in enumerate(cars):
            output = nets[i].activate(car.get_data())
            choice = output.index(max(output))
            if choice == 0:
                car.angle += 10 # Gauche
            elif choice == 1:
                car.angle -= 10 # Droite
            elif choice == 2:
                if(car.speed - 2 >= 12):
                    car.speed -= 2 # Ralentir
            else:
                car.speed += 2 # Accélérer
        
        # Vérifier si la voiture est toujours en vie
        # Augmenter la forme physique si oui et quitter la boucle sinon
        still_alive = 0
        for i, car in enumerate(cars):
            if car.is_alive():
                still_alive += 1
                car.update(game_map)
                genomes[i][1].fitness += car.get_reward()

        if still_alive == 0:
            break

        counter += 1
        if counter == 30 * 40: # Arrêter après environ 20 secondes
            break

        # Dessiner la carte et toutes les voitures qui sont en vie
        screen.blit(game_map, (0, 0))
        for car in cars:
            if car.is_alive():
                car.draw(screen)
        
        # Afficher les informations
        text = generation_font.render("Génération : " + str(current_generation), True, (0,0,0))
        text_rect = text.get_rect()
        text_rect.center = (900, 450)
        screen.blit(text, text_rect)

        text = alive_font.render("Toujours en vie : " + str(still_alive), True, (0, 0, 0))
        text_rect = text.get_rect()
        text_rect.center = (900, 490)
        screen.blit(text, text_rect)

        pygame.display.flip()
        clock.tick(60) # 60 FPS

if __name__ == "__main__":
    
    # Charger la configuration
    config_path = "./config.txt"
    config = neat.config.Config(neat.DefaultGenome,
                                neat.DefaultReproduction,
                                neat.DefaultSpeciesSet,
                                neat.DefaultStagnation,
                                config_path)

    # Créer la population et ajouter des rapporteurs
    population = neat.Population(config)
    population.add_reporter(neat.StdOutReporter(True))
    stats = neat.StatisticsReporter()
    population.add_reporter(stats)
    
    # Lancer la simulation pour un maximum de 1000 générations
    population.run(run_simulation, 1000)