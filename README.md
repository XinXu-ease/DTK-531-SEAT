# DTK-531-W5
**System Functionality Overview**

The Smart Seating Kit is an intelligent, dual-module, AI-enabled system that learns users’ unique posture habits in sedentary environments, thus protecting users’ spine. By synchronizing a pressure-sensing seat with an infrared-sensing backrest, the system detects unhealthy posture habits and provides personalized, tangible interventions.
Key Features & Workflows

1. Prolonged Sedentary Behavior: 
The system maintains a Prolonged Sitting Timer (time_sit) that tracks continuous occupancy. Once the threshold is exceeded, the system triggers a combined Visual Dashboard Alert and Vibration Pulse to encourage the user to stand up and move.

3. Unbalanced Sitting Patterns (e.g., Crossing Legs):
Integrated Pressure Sensors in the seat cushion detect center-of-gravity shifts. An AI-refined threshold (thres_blc) - personalized to the user’s body type - tracks the duration of the imbalance (time_blc), providing a Vibration Reminder to guide the user back to a balanced posture.

5. Poor Spinal Alignment (e.g., Slouching):
Infrared Reflective Sensors in the backrest monitor distance gaps to identify slouching or "hollow back" positions. It also has an AI-refined threshold (thres_sp). After a certain time duration of poor position (time_sp), the system activates a Pneumatic Support Module, inflating a lumbar pillow to provide physical reinforcement and a tangible reminder to sit upright.

**Data Flow**

Sensing & Data Translation: Sensors (Pressure sensors in Seat module to detect center-of-gravity and Infrared reflective sensors in Backrest module for monitor upper-body posture) capture raw physical signals and convert them into JSON-formatted data packets (e.g., pressure matrices and distance values). 
Communication through MQTT: These packets are transmitted via the MQTT protocol to a backend processing unit at a frequency of 1Hz–5Hz to ensure real-time synchronization between the seat and backrest.

Timing System: Three independent timers track Prolonged Sitting (time_sit), Unbalanced Posture  (time_blc), and Slouching (time_sp).
AI Decision Logic: The backend LLM parses the JSON data, compares it against personalized AI thresholds (dynamic based on user feedback), and updates the cumulative timers for each posture category.

Actuation & Verification:
If a threshold is breached, the system publishes a command via MQTT to trigger the hardware actuators (vibration motor or air pump) and the software UI.
The system then enters a Verification Phase, checking for a change in sensor data. If the posture is corrected, timers are reset; if not, reminders are repeated after a designated interval.

**Pseudocode Implementation:** Refer to the diagram
