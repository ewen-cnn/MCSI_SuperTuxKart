from STK_main_client import GREEN, WHITE, BLUE

###############################################################################
## Representation de l'etat du kart
class KartState:

    # etat -> (commande "pressed", commande "released")
    STEERING_COMMANDS = {
        'LEFT':  ('P_LEFT',  'R_LEFT'),
        'RIGHT': ('P_RIGHT', 'R_RIGHT'),
        'NONE':  (None,      None),
    }
    THROTTLE_COMMANDS = {
        'ACCELERATE': ('P_ACCELERATE', 'R_ACCELERATE'),
        'BRAKE':      ('P_BRAKE',      'R_BRAKE'),
        'NONE':       (None,           None),
    }

    def __init__(self, sender, debug=False):
        self.sender = sender
        self.debug = debug
        self.steering = 'NONE'
        self.throttle = 'NONE'
        self.skidding_on = False
        self.nitro_on = False

    def _switch(self, table, current, target):
        """Relache l'ancienne touche puis appuie sur la nouvelle."""
        if target == current:
            return current
        release_old = table[current][1]
        if release_old:
            self.sender.send(release_old)
        press_new = table[target][0]
        if press_new:
            self.sender.send(press_new)
        if self.debug:
            print(BLUE + '\tetat : {} -> {}'.format(current, target) + WHITE)
        return target

    def set_steering(self, target):
        self.steering = self._switch(self.STEERING_COMMANDS, self.steering, target)

    def set_throttle(self, target):
        self.throttle = self._switch(self.THROTTLE_COMMANDS, self.throttle, target)

    def release_all(self):
        """Retour au point neutre : roues droites, ni accelerateur ni frein."""
        self.set_steering('NONE')
        self.set_throttle('NONE')

    # --- Actions ponctuelles (le serveur fait press_and_release) -------------
    def fire(self):
        """Lance un objet."""
        self.sender.send('FIRE')

    def rescue(self):
        """Sauvetage par l'oiseau : replace le kart sur la piste."""
        self.sender.send('RESCUE')

    def set_skidding(self, active):
        """Maintient la touche de derapage tant que active est vrai."""
        if active == self.skidding_on:
            return                          # pas de changement : rien a envoyer
        self.sender.send('P_SKIDDING' if active else 'R_SKIDDING')
        self.skidding_on = active
        if self.debug:
            print(BLUE + '\tderapage : {}'.format('ON' if active else 'OFF') + WHITE)

    def set_nitro(self, active):
        """Maintient la touche nitro tant que active est vrai."""
        if active == self.nitro_on:
            return
        self.sender.send('P_NITRO' if active else 'R_NITRO')
        self.nitro_on = active
        if self.debug:
            print(GREEN + '\tdouble-tap -> NITRO' + WHITE)

    def release_all(self):
        """Retour au point neutre : roues droites, ni accelerateur ni frein."""
        self.set_steering('NONE')
        self.set_throttle('NONE')
        self.set_skidding(False)

    def __str__(self):
        if self.steering == 'NONE' and self.throttle == 'NONE':
            return 'immobile'
        return '{} + {}'.format(self.steering, self.throttle)

