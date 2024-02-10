import neopixel
import board
from analogio import AnalogIn
import rotaryio
from digitalio import DigitalInOut, Direction, Pull
from adafruit_debouncer import Debouncer
from time import sleep, monotonic
import json
from math import sqrt


config = {'start_color': 'green',
          'light_threshold': 1000,
          'loop_cycle_time': 0.05,
          'running_average': {
            'window_size':10,
            'threshold':3.0
          },
          'rainbow': {'cycle_time': 0.3},
          'encoder': {
            "max_position": 20,
		    "start_position": 20
          }
        }

try:
    with open('/config.json', 'r') as fp:
        config = json.load(fp)
except (OSError, ValueError) as e:
    pass

# Constants
sw = board.GP16
dt = board.GP13
clk = board.GP14
photo_resistor_pin = board.GP26
neopixel_data_pin = board.GP0

color_names = ['white',
               'yellow',
               'orange',
               'red',
               'pink',
               'purple',
               'blue',
               'cyan',
               'green',
               'lime green',
               'rainbow',
               'off'
]

colors = [(255, 255, 255),  # white
          (255, 255, 000),  # yellow
          (255, 165, 000),  # orange
          (255, 000, 000),  # red
          (255, 192, 203),  # pink
          (255, 000, 255),  # purple
          (000, 000, 255),  # blue
          (000, 255, 255),  # cyan
          (000, 255, 000),  # green
          ( 50, 205,  50),  # lime green
          ( -1,  -1,  -1),  # rainbow
          (000, 000, 000)]  # off

color_mapping = {color_names[i]: i for i in range(len(colors))}

# Config
# Start Color
color_index = color_mapping[config.get('start_color', 'green')]
# photo transistor
light_threshold = config.get('light_threshold', 1000)
# outlier detect
window_size = config.get('running_average', {'window_size':10}).get('window_size', 10)
threshold = config.get('running_average', {'threshold':3.0}).get('threshold', 40.0)
# rainbow
cycle_time = config.get('rainbow', {'cycle_time': 0.03}).get('cycle_time', 0.3)
# encoder
max_position = config.get('encoder', {"max_position": 20}).get('max_position', 20)
start_position = config.get('encoder', {"start_position": 20}).get('start_position', 20)
# loop cycle time
loop_cycle_time = config.get('loop_cycle_time', 0.05)


class Wheel:
    def __init__(self, cycle_time=0.3):
        self.num_steps = 255
        self.step = 0
        self.last_update_time = monotonic()
        self.cycle_time = cycle_time
        self.rgb = (255, 255, 255)

    def update(self):
        # Increment the step to simulate rotation
        self.step = (self.step + 1) % self.num_steps

    def get_color(self):
        # Calculate RGB values based on the current step
        # Calculate RGB values based on the current step
        if (monotonic() - self.last_update_time) > self.cycle_time:
            self.update()
            pos = self.step
            # Input a value 0 to 255 to get a color value.
            # The colors are a transition r - g - b - back to r.
            if pos < 0 or pos > 255:
                r = g = b = 0
            elif pos < 85:
                r = int(pos * 3)
                g = int(255 - pos * 3)
                b = 0
            elif pos < 170:
                pos -= 85
                r = int(255 - pos * 3)
                g = 0
                b = int(pos * 3)
            else:
                pos -= 170
                r = 0
                g = int(pos * 3)
                b = int(255 - pos * 3)
            self.last_update_time = monotonic()
            self.rgb = r, g, b
        return self.rgb

class ButtonState:
    def __init__(self, button_pin):
        button = DigitalInOut(button_pin)
        button.direction = Direction.INPUT
        button.pull = Pull.UP
        self.button = Debouncer(button)

    def update(self):
        self.button.update()

    def pressed(self):
        return self.button.rose

class BoundedEncoder:
    def __init__(self, dt, clk, max_position=20, start_position=20):
        self.encoder = rotaryio.IncrementalEncoder(dt, clk)
        if 0 <= start_position <= max_position:
            self.encoder.position = start_position
        else:
            self.encoder.position = max_position
        self.min = 0
        self.max = max_position

    def _update(self):
        if self.encoder.position > self.max:
            self.encoder.position = self.max
        elif self.encoder.position < self.min:
            self.encoder.position = self.min

    def position(self):
        self._update()
        return self.encoder.position

class OutlierDetector:
    def __init__(self, start=0.0, window_size=100, threshold=2.0):
        self.window_size = window_size
        self.threshold = threshold
        self.samples = [start] * window_size
        self.sum = sum(self.samples)
        self.index = 0

    def _update(self, new_value):
        old_value = self.samples[self.index]
        self.samples[self.index] = new_value

        self.sum += new_value - old_value

        self.index = (self.index + 1) % self.window_size

    def compute_running_average(self):
        return self.sum / self.window_size

    def compute_running_std_dev(self):
        average = self.compute_running_average()
        mean_squared = sum((i - average) ** 2 for i in self.samples)
        return sqrt(mean_squared/self.window_size)

    def is_outlier(self, new_value):
        self._update(new_value)
        average = self.compute_running_average()
        std_dev = (self.compute_running_std_dev() / self.window_size) ** 0.5
        return abs(new_value - average) > (self.threshold * std_dev)

# Button Setup
button = ButtonState(button_pin=sw)

# Neopixel Setup
pixels = neopixel.NeoPixel(neopixel_data_pin, 1)
pixels[0] = colors[color_index]

# Photo Transistor Setup
photo_resistor = AnalogIn(photo_resistor_pin)
outlier_detector = OutlierDetector(start=photo_resistor.value, window_size=window_size, threshold=threshold)

# Encoder Setup
encoder = BoundedEncoder(dt, clk, max_position, start_position)

# Wheel Setup
wheel = Wheel(cycle_time=cycle_time)

while True:
    button.update()
    brightness = encoder.position() * (1.0/encoder.max)

    if brightness == 0:
        pixels.brightness = 0
    else:
        if button.pressed():
            color_index += 1
            color_index = color_index % len(colors)
        if colors[color_index] == (-1,-1,-1):
            write_color = wheel.get_color()
        else:
            write_color = colors[color_index]

        external_brightness = photo_resistor.value
        if outlier_detector.is_outlier(external_brightness):
            external_brightness = outlier_detector.compute_running_average()

        if external_brightness > light_threshold:
           pixels.brightness = 0
        else:
            pixels[0] = write_color
            pixels.brightness = brightness
    sleep(loop_cycle_time)
