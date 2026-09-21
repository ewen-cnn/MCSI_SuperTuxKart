// Confguration  
const int ledPin=13;

void setup() {
    Serial.begin(115200);
    delay(200);
    pinMode(ledPin,OUTPUT);
    //while (!Serial) {
      ; // wait for serial port to connect. Needed for native USB
    //}
}

void loop() {
    int sensorState = digitalRead(2);
    delay(100);
    if(sensorState == HIGH)
    {
        digitalWrite(ledPin,HIGH);
        Serial.println("vibrationSensor: ", sensorState)
    }
    else
    {
        digitalWrite(ledPin,LOW);
    }
}
