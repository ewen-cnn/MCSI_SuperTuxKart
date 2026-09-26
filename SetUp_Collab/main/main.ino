// Confguration

const int ledPin=13;
const int PIN_VIBRATION = 2;

int max_analog_dta      = 300;              // max analog data
int min_analog_dta      = 100;              // min analog data
int static_analog_dta   = 0;                // mean analog data

bool previous_vibrationSensor = false;

bool contraction_detected = false;
bool previous_contraction = false;
bool state = false;

// get analog value
int getAnalog(int pin)
{
  long sum = 0;
  for(int i=0; i<32; i++)
  {
    sum += analogRead(pin);
  }
  int dta = sum>>5;
  max_analog_dta = dta>max_analog_dta ? dta : max_analog_dta;         // if max data
  min_analog_dta = min_analog_dta>dta ? dta : min_analog_dta;         // if min data
  return sum>>5;
}

void calibration(){
    long sum = 0;
    for(int i=0; i<=10; i++)
    {
        for(int j=0; j<100; j++)
        {
            sum += getAnalog(A0);
            delay(1);
        }
    }
    sum /= 1100;
    static_analog_dta = sum;
    Serial.print("static_analog_dta = ");
    Serial.println(static_analog_dta);
}


void setup() {
    Serial.begin(115200);
    pinMode(ledPin,OUTPUT);
    while (!Serial) {
      ; // wait for serial port to connect. Needed for native USB
      }
    calibration();
}

void loop() {
    int vibrationSensor = digitalRead(PIN_VIBRATION);
    int muscleSensor = analogRead(A0);

    if(vibrationSensor == HIGH and previous_vibrationSensor == LOW)
    {
      digitalWrite(ledPin,HIGH);
      Serial.println("vibrationSensor");
    }
    else{
      digitalWrite(ledPin,LOW);
    }
    previous_vibrationSensor = vibrationSensor;

    if (contraction_detected = ( muscleSensor > static_analog_dta - 10 )){         
      if (contraction_detected && !previous_contraction) //nouvelle contraction détectée
      {
        state=!state;
        Serial.println("Contraction");
      }
    }
    previous_contraction = contraction_detected;
}
