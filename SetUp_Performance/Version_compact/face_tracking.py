######################################################################################
# This python script implements a 3D face tracking which uses a webcam               #
# to achieve face detection. This face detection is done with MediaPipe:             #
#                                                                                    #
# The script then streams the 3D position through OSC                                #
#                                                                                    #
# date: December 2019                                                                #
# authors: Cedric Fleury                                                             #
# affiliation: IMT Atlantique, Lab-STICC (Brest)                                     #
#                                                                                    #
# usage: python tracking.py x                                                        #
# where x is an optional value to tune the interpupillary distance of the            #
# tracked subject (by default, the interpupillary distance is set at 6cm).           #
######################################################################################

# import necessary modules
import sys
import time
import math
import threading 
import numpy as np
from typing import Tuple, Union

# import oscpy for OSC streaming (https://pypi.org/project/ocspy/)
from oscpy.client import OSCClient

# import opencv for image processing
import cv2

# import mediapipe for face detection
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


########## Part 3: compute the focal length of the webcam ###########

# define the camera focal length in pixels
# Use the calbirate.py script to determine it!
fl = 654.0


################## Part 4: compute the 3D position ##################

# define the height of your screen in cm
screen_heigth = 21.0 

# define the default interpupillary distance
user_ipd = 3

# Set interpupillary distance from the command parameter
if len(sys.argv) >= 2:
    user_ipd = float(sys.argv[1])

print("Tracking initialized with an interpupillary distance of " + str(user_ipd) + " cm")




# define address and port for streaming
address = 'localhost'
port = 8000

clientOSC = OSCClient(address, port)
print("OSC connection established to " + address + " on port " + str(port) + "!")




# capture frames from a camera and the time 
cap = cv2.VideoCapture(0)
first_time = time.time()*1000.0

# get image size
frame_width  = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
frame_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
print("Video size: " + str(frame_width) + " x " + str(frame_height))


################# Part 1: understand how the face dectector works #################

# Create a new class for retrieving and storing the tracking results
class TrackingResults:
    tracking_results = None
    def get_result(self, result: vision.FaceDetectorResult, output_image: mp.Image, timestamp_ms: int):
            self.tracking_results = result
    
res = TrackingResults()

# Create a face detector instance with the live stream mode:
base_options = python.BaseOptions(model_asset_path='blaze_face_short_range.tflite')
options = vision.FaceDetectorOptions(
    base_options=base_options,
    running_mode=vision.RunningMode.LIVE_STREAM,
    result_callback=res.get_result)
detector = vision.FaceDetector.create_from_options(options)


#### visualization fonctions ####

MARGIN = 10  # pixels
ROW_SIZE = 10  # pixels
FONT_SIZE = 1
FONT_THICKNESS = 2
TEXT_COLOR = (255, 0, 0)  # red

def _normalized_to_pixel_coordinates(
    normalized_x: float, normalized_y: float, image_width: int,
    image_height: int) -> Union[None, Tuple[int, int]]:
  """Converts normalized value pair to pixel coordinates."""

  # Checks if the float value is between 0 and 1.
  def is_valid_normalized_value(value: float) -> bool:
    return (value > 0 or math.isclose(0, value)) and (value < 1 or
                                                      math.isclose(1, value))

  if not (is_valid_normalized_value(normalized_x) and
          is_valid_normalized_value(normalized_y)):
    # TODO: Draw coordinates even if it's outside of the image bounds.
    return None
  x_px = min(math.floor(normalized_x * image_width), image_width - 1)
  y_px = min(math.floor(normalized_y * image_height), image_height - 1)
  return x_px, y_px

def visualize(
    image,
    detection_result
) -> np.ndarray:
  """Draws bounding boxes and keypoints on the input image and return it.
  Args:
    image: The input RGB image.
    detection_result: The list of all "Detection" entities to be visualize.
  Returns:
    Image with bounding boxes.
  """
  annotated_image = image.copy()
  height, width, _ = image.shape


  for detection in detection_result.detections:
    # Draw bounding_box
    bbox = detection.bounding_box
    start_point = bbox.origin_x, bbox.origin_y
    end_point = bbox.origin_x + bbox.width, bbox.origin_y + bbox.height
    cv2.rectangle(annotated_image, start_point, end_point, TEXT_COLOR, 3)



    # Draw keypoints
    #for keypoint in detection.keypoints:
    #  keypoint_px = _normalized_to_pixel_coordinates(keypoint.x, keypoint.y,
    #                                                width, height)
    # color, thickness, radius = (0, 255, 0), 2, 2
    # cv2.circle(annotated_image, keypoint_px, thickness, color, radius)
    # TODO: comment the previous section

    #### Part 2: get the position of the eyes and compute the center of the eyes ####
    # Draw only the keypoints corresponding to the eyes
  for i in range(2):
    keypoint = detection.keypoints[i]
    keypoint_px = _normalized_to_pixel_coordinates(keypoint.x, keypoint.y,
                                                    width, height)
    color, thickness, radius = (0, 255, 0), 2, 2

    if keypoint_px is not None:
        cv2.circle(annotated_image, keypoint_px, thickness, color, radius)


    # Draw the center of the eyes with a different color
    if len(detection.keypoints) >= 2:
        eye1 = _normalized_to_pixel_coordinates(detection.keypoints[0].x, detection.keypoints[0].y,
                                                width, height)
        eye2 = _normalized_to_pixel_coordinates(detection.keypoints[1].x, detection.keypoints[1].y,
                                                width, height)
        if eye1 is not None and eye2 is not None:
            center_x = int((eye1[0] + eye2[0]) / 2)
            center_y = int((eye1[1] + eye2[1]) / 2)
            cv2.circle(annotated_image, (center_x, center_y), 3, (0, 0, 255), -1)  # Blue color for the center of the eyes

    # Draw label and score
    category = detection.categories[0]
    category_name = category.category_name
    category_name = '' if category_name is None else category_name
    probability = round(category.score, 2)
    result_text = category_name + ' (' + str(probability) + ')'
    text_location = (MARGIN + bbox.origin_x,
                     MARGIN + ROW_SIZE + bbox.origin_y)
    cv2.putText(annotated_image, result_text, text_location, cv2.FONT_HERSHEY_PLAIN,
                FONT_SIZE, TEXT_COLOR, FONT_THICKNESS)

  return annotated_image

#####################################################################################

######################### Part 4: compute the 3D position ###########################

# convert the 2 position in pixels in the image to 
# a 3D position in cm in the camera reference frame
def compute3DPos(ibe_x, ibe_y, rec_ipd):
    
    # compute the distance between the head and the camera
    
    z = (fl * user_ipd*2) / rec_ipd

    # compute the x and y coordinate in a Yup reference frame
    
    cx = frame_width / 2.0
    cy = frame_height / 2.0

    x = ((ibe_x - cx) * z)/fl
    y = ((ibe_y - cy) * z)/fl

    # center the reference frame on the center of the screen
    # (and not on the camera)
    if screen_heigth > 0:
        y = y - (screen_heigth / 2.0)
    
    return (x, y, z)





################################ main fonction ##############################
    
def runtracking():

    print("\nTracking started !!!")
    print("Hit ESC key to quit...")
    
    # infinite loop for processing the video stream
    while True:

        # add to delay to avoid that the loop run too fast
        time.sleep(0.05)

        # read one frame from a camera and get the frame timestamp
        ret, img_bgr = cap.read()
        frame_timestamp_ms = int(time.time()*1000 - first_time)

        # Convert the opencv image to RGB
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        # Convert the frame received from OpenCV to a MediaPipe’s Image object.
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb) 

        # Send live image data to perform face detection.
        # The results are accessible via the `result_callback` provided in
        # the `FaceDetectorOptions` object.
        # The face detector must be created with the live stream mode.
        detector.detect_async(mp_image, frame_timestamp_ms)

        if res.tracking_results != None:
            #### Part 2: get the position of the eyes and compute the center of the eyes ####

            # If a face is detected
            # Get the biggest face 
            if len (res.tracking_results.detections) > 0:
                biggest_face = max(res.tracking_results.detections, 
                                   key=lambda det: 
                                   det.bounding_box.width * det.bounding_box.height)
                

            # Get the position of the two eyes in pixels 
            if len( biggest_face.keypoints) >=2:
                eye1 = biggest_face.keypoints[0]
                eye2 = biggest_face.keypoints[1]

                if eye1 is not None and eye2 is not None:
                    eye1_px =_normalized_to_pixel_coordinates(eye1.x, eye1.y,
                                                              int(frame_width), int(frame_height))
                                        
                    eye2_px = _normalized_to_pixel_coordinates(eye2.x, eye2.y,
                                                              int(frame_width), int(frame_height))

                if eye1_px is not None and eye2_px is not None:
                    print("Eye 1:", eye1_px)
                    print("Eye 2:", eye2_px)

                  # If we have a position for the two eyes
                    # compute the position between the two eyes (in pixels)
                    eye_center_x = int((eye1_px[0] + eye2_px[0]) / 2)
                    eye_center_y = int((eye1_px[1] + eye2_px[1]) / 2)
                    
                    
                    eye_center = (int (eye_center_x), int (eye_center_y)) 

                    print("Eye center:", eye_center)

                    # compute the interpupillary distance (in pixels)
                    distance_interpupi= math.sqrt((eye2_px[0] - eye1_px[0])**2 + (eye2_px[1] - eye1_px[1])**2)

                    print ("Distance interpupille", distance_interpupi)


                    ###################### Part 4: compute the 3D position ###########################
                    # compute the 3D position in the reference frame of the screen center
                    pos_x, pos_y, pos_z = compute3DPos(eye_center_x, eye_center_y, distance_interpupi)

                    print("3D position: " + "{:.2f}".format(pos_x) + " - " 
                    											+ "{:.2f}".format(pos_y) + " - " 
                    											+ "{:.2f}".format(pos_z))

                    ################### Part 5: send the head position with OSC ######################
                    clientOSC.send_message(b'/tracker/head/pos_xyz', [pos_x, pos_y, pos_z])
  
            # Display an image in a window (you can avoid to display the image to improve the performance)
            annotated_image = mp_image.numpy_view()
            annotated_image = visualize(annotated_image, res.tracking_results)
            bgr_annotated_image = cv2.cvtColor(annotated_image, cv2.COLOR_RGB2BGR)
            cv2.imshow('img', bgr_annotated_image)
  
        # Wait for Esc key to stop 
        k = cv2.waitKey(30) & 0xff
        if k == 27: 
               break
  
    # release the video stream from the camera
    cap.release()
      
    # close the associated window 
    cv2.destroyAllWindows() 


############################ program execution #############################
            
runtracking()