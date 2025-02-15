from fastapi import FastAPI, Request, HTTPException, File, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
import os
from Chat.IntelChat.NeuralChat7B import NeuralNet7B
from Chat.GPT2.gpt2 import FineTunedGPT2
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from Chat.Gemini.gemini import GetGeminiOutput
import json
from dotenv import load_dotenv
from datetime import datetime
import shutil
from time import perf_counter

# This calls the OpenVino Model
# Do no delete at all costs 💀💀💀
from intel.toolkit.gesture_function import run_gesture_recognition


cred = credentials.Certificate("./firebase-admin.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
# Initialize FastAPI app
app = FastAPI()
# Initialize NeuralNet
nn = NeuralNet7B()
gpt2 = FineTunedGPT2()
# Initialize Firebase Admin SDK



# Initialize Gemini model
load_dotenv()
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
gemini_model = GetGeminiOutput(API_KEY=GOOGLE_API_KEY, max_tokens=3000, temperature=0.7)

# Load the JSON file
with open('result.json', 'r') as json_file:
    data = json.load(json_file)

with open('family_links.json', 'r') as family_file:
    family_links_data = json.load(family_file)

with open('common_links.json', 'r') as common_file:
    common_links_data = json.load(common_file)

with open('question_links.json', 'r') as question_file:
    question_links_data = json.load(question_file)

# Create a dictionary to store gloss-link mappings
gloss_link_mapping = {item['gloss']: item['link'] for item in data}

# Function to get links corresponding to words in a sentence
def get_links_for_sentence(sentence):
    """
    This function takes a sentence as input and returns a list of dictionaries containing words and their corresponding links from the gloss_link_mapping.
    """

    words = [word.lower() for word in sentence.split()]
    result_objects = []
    for word in words:
        # Check if the word's gloss exists in the mapping
        if word in gloss_link_mapping:
            result_objects.append({
                'word': word,
                'link': gloss_link_mapping[word]
            })
    return result_objects

# Function to push a chat message to Firebase under the user's chats array
def push_chat_message(user_id, message, sender):
    """
    Pushes a chat message to the Firestore database for a given user.

    Parameters:
        user_id (str): The ID of the user.
        message (str): The text of the chat message.
        sender (str): The sender of the chat message.

    Returns:
        None

    Raises:
        None
    """

    user_ref = db.collection('Users').document(user_id)
    user_data = user_ref.get().to_dict()
    timestamp = datetime.now()
    if user_data is None:
        # Create the user document if it doesn't exist
        user_ref.set({
            'chats': [{'text': message, 'sender': sender, 'timestamp': timestamp}]
        })
    else:
        # Update the existing user document to add the new chat message
        user_ref.update({

            'chats': firestore.ArrayUnion([{'text': message, 'sender': sender, 'timestamp': timestamp}])
        })
        print('Updated chat history for user:', message)

# Function to retrieve chat history from Firebase for a specific user
def get_chat_history(user_id):
    """
    Retrieves the chat history for a given user from the database.

    Parameters:
        user_id (str): The unique identifier of the user.

    Returns:
        list: A list of dictionaries representing the chat history. Each dictionary contains the 'text' and 'sender' fields of a chat message. If the user does not have a chat history or the 'chats' field is missing in the user data, an empty list is returned.
    """
    user_ref = db.collection('Users').document(user_id)

    print('Retrieving chat history for user:', user_id)
    user_data = user_ref.get().to_dict()
    if user_data and 'chats' in user_data:
        # Exclude timestamps and handle missing 'sender' field
        chat_history = []
        for message in user_data['chats']:
            chat_message = {'text': message.get('text', ''), 'sender': message.get('sender', 'Unknown')}
            chat_history.append(chat_message)
        return chat_history
    else:
        return []

# Request models
class InputData(BaseModel):
    input_sequence: str
    uid: str

class LinksResponse(BaseModel):
    links: List[dict]

# Routes
@app.get('/')
def start():
    return gemini_model.starting_statement()

# Gemini's output route
@app.post('/get_gemini_output')
def get_output(data: InputData):
    response = gemini_model.answers(data.input_sequence)
    # Push user message to Firebase under the user's chats array
    push_chat_message(data.uid, data.input_sequence, 'user')
    push_chat_message(data.uid, response, 'bot')
    # Return response as JSON
    return {'response': response}

# Intel's Neural Chat 7B output route
@app.post('/get_intel_output')
def get_intel_output(data: InputData):
    response = nn.predict(data.input_sequence)
    # Push user message to Firebase under the user's chats array
    # push_chat_message(data.uid, data.input_sequence, 'user')
    # push_chat_message(data.uid, response, 'neural_bot')
    
    # Return response as JSON
    return {'response': response}


# History route
@app.post('/history')
async def fetch_chat_history(request: Request):
    
    data = await request.json()
    user_id = data.get('uid', '')  # Retrieve uid from request data
    # Retrieve chat history from Firebase for the specified user
    history = get_chat_history(user_id)
    # Return chat history as JSON
    return {'response': history}


# Get links route
@app.post('/get_links')
def get_links(data: dict):
    input_sentence = data.get('input_sentence', '')
    # Get links corresponding to words in the input sentence
    result_links = get_links_for_sentence(input_sentence)
    return {'links': result_links}

@app.get("/test")
def test():
    return {"message": "Hello World"}


# To save Videos in Local Store
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
video_dir = os.path.join(BASE_DIR, "temp_videos")


# This route allows us to work 
@app.post("/upload-video-file/")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Uploads a video file and performs gesture recognition on it.

    Parameters:
        - background_tasks (BackgroundTasks): A background tasks object.
        - file (UploadFile): The video file to be uploaded.

    Returns:
        - JSONResponse: A JSON response containing the message, labels, upload time, and processing time.

    Raises:
        - None

    Notes:
        - The video file is saved in the `video_dir` directory.
        - The gesture recognition models are located in the `BASE_DIR` directory.
        - The class map file is located in the `BASE_DIR` directory.
        - The video processing is performed using the CPU device.
        - The video directory is deleted after processing.
    """
    
    if(not os.path.exists(video_dir)):
        os.makedirs(video_dir, exist_ok=True)
    
    video_path = os.path.join(video_dir, file.filename)
    
    start_time = perf_counter()

    
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    upload_time = perf_counter() - start_time
    print(f"File upload and save time: {upload_time:.2f} seconds")

    
    action_model = os.path.join(BASE_DIR, "intel", "asl-recognition-0004", "FP16", "asl-recognition-0004.xml")
    detection_model = os.path.join(BASE_DIR, "intel", "person-detection-asl-0001", "FP16", "person-detection-asl-0001.xml")
    class_map_path = os.path.join(BASE_DIR, "intel", "msasl100.json")
    device = "CPU"  

    
    processing_start_time = perf_counter()
    
    labels = run_gesture_recognition(
        action_model,
        detection_model,
        video_path,
        class_map_path=class_map_path,
        device=device,
        no_show=True
    )

    translated_text = " ".join(labels)

    processing_time = perf_counter() - processing_start_time
    print(f"Video processing time: {processing_time:.2f} seconds")

    if os.path.exists(video_dir):
        shutil.rmtree(video_dir)

    return JSONResponse(content={"message": "Video received and processing started.", "labels": list(labels), "upload-time":upload_time, "performance_time": processing_time}, status_code=200)


from fastapi import FastAPI, WebSocket
from aiortc import RTCPeerConnection, MediaStreamTrack, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaBlackhole, MediaRelay, MediaPlayer, MediaRecorder
import aiortc.mediastreams as ms
import uuid
import json
import os
import cv2
from av import VideoFrame
ROOT = os.path.dirname(__file__)

# app = FastAPI()

relay = MediaRelay()  # Provide the path to where you want to record

# This dictionary stores the peer connections
peer_connections = {}

import sys
from pathlib import Path
import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[2] / 'common/python'))
sys.path.append(str(Path(__file__).resolve().parents[2] / 'common/python/model_zoo'))

from intel.toolkit.gesture_recognition_demo.common import load_core
from intel.toolkit.gesture_recognition_demo.video_library import VideoLibrary
from intel.toolkit.gesture_recognition_demo.person_detector import PersonDetector
from intel.toolkit.gesture_recognition_demo.tracker import Tracker
from intel.toolkit.gesture_recognition_demo.action_recognizer import ActionRecognizer
from intel.toolkit.model_api.performance_metrics import PerformanceMetrics

live_labels = set()

DETECTOR_OUTPUT_SHAPE = -1, 5
TRACKER_SCORE_THRESHOLD = 0.4
TRACKER_IOU_THRESHOLD = 0.3
ACTION_IMAGE_SCALE = 256
OBJECT_IDS = [ord(str(n)) for n in range(10)]
action_model = os.path.join(ROOT, "intel", "asl-recognition-0004", "FP16", "asl-recognition-0004.xml")
detection_model = os.path.join(ROOT, "intel", "person-detection-asl-0001", "FP16", "person-detection-asl-0001.xml")
class_map_path = os.path.join(ROOT, "intel", "msasl100.json")

def load_class_map( file_path):
    if file_path is not None and os.path.exists(file_path):
        with open(file_path, 'r') as input_stream:
            print("Loading class map from", file_path)
            data = json.load(input_stream)
            return dict(enumerate(data))
    return None

device = 'CPU'
core = load_core()
class_map = load_class_map(class_map_path)
person_detector = PersonDetector(detection_model, device, core, num_requests=2, output_shape=DETECTOR_OUTPUT_SHAPE)
action_recognizer = ActionRecognizer(action_model, device, core, num_requests=2, img_scale=ACTION_IMAGE_SCALE, num_classes=len(class_map))
person_tracker = Tracker(person_detector, TRACKER_SCORE_THRESHOLD, TRACKER_IOU_THRESHOLD)
metrics = PerformanceMetrics()
action_threshold = 0.8


class WebSocketVideoStream:
    def __init__(self):
        self.frames = []

    def add_frame(self, frame):
        self.frames.append(frame)
    
    def len_frame(self):
        return len(self.frames)

    def get_live_frame(self):
        if self.frames:
            return self.frames[-1]
        return None

    def get_batch(self, batch_size):
        if len(self.frames) >= batch_size:
            batch = self.frames[-batch_size:]
            self.frames = self.frames[-16:]
            return batch
        return None
    

video_stream = WebSocketVideoStream()

class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from another track.
    """

    kind = "video"

    def __init__(self, track, transform):
        super().__init__()  # don't forget this!
        self.track = track
        self.transform = transform
        # self.labels_found=set()

    async def recv(self):
        rawFrame = await self.track.recv()
        frame = rawFrame.to_ndarray(format="bgr24")
        video_stream.add_frame(frame)
        # print(action_recognizer.input_length)
        # print(frame.shape)
        # print(video_stream.len_frame())
        batch = video_stream.get_batch(action_recognizer.input_length)
        try:
            if batch:
                # print("running")
                detections, _ = person_tracker.add_frame(frame, len(OBJECT_IDS), {})
                if detections is not None:
                    
                    for detection in detections:
                        # print(detection.roi.reshape(-1))
                        # print("running")
                        recognizer_result = action_recognizer(batch, detection.roi.reshape(-1))
                        if recognizer_result is not None:
                            action_class_id = np.argmax(recognizer_result)
                            action_score = np.max(recognizer_result)
                            if action_score >= action_threshold:
                                action_label = class_map[action_class_id]
                                live_labels.add(action_label)
                                print(f'Action ID: {action_class_id}, Score: {action_score}, Label: {action_label}')
                               
                        else:
                            print("No recognizer result")
                    
                else:
                    print("No detections")
            else:
                print("No batch available")
        except Exception as e:
            print(f"An error occurred: {e}")
        return rawFrame



async def handle_offer(websocket: WebSocket, pc: RTCPeerConnection, message: dict):
    print(message["offer"]["sdp"])
    offer = RTCSessionDescription(
        sdp=message["offer"]["sdp"], type=message["offer"]["type"]
    )
    await pc.setRemoteDescription(offer)
    print("set remote description")

    recorder = MediaBlackhole()
    

    answer = await pc.createAnswer()
    print(answer.sdp)
    await pc.setLocalDescription(answer)

    await websocket.send_text(json.dumps({
        "type": "answer",
        "answer": {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
    }))

async def handle_candidate(pc: RTCPeerConnection, message: dict):
    candidate_info = message["candidate"]["candidate"].split()
    candidate = RTCIceCandidate(
        candidate_info[1], candidate_info[0], candidate_info[4], 
        int(candidate_info[5]), int(candidate_info[3]), candidate_info[2], 
        candidate_info[7],
        sdpMid=message["candidate"]["sdpMid"], sdpMLineIndex=message["candidate"]["sdpMLineIndex"]
    )
    await pc.addIceCandidate(candidate)

async def handle_end_track(websocket: WebSocket, recorder: MediaBlackhole):
    await websocket.send_text(json.dumps({"type": "track_end"}))
    await recorder.stop()
    print("Track ended")


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    pc = RTCPeerConnection()
    peer_connections[client_id] = pc

    @pc.on("track")
    async def on_track(track):
        if track.kind == "video":
            pc.addTrack(
                VideoTransformTrack(
                    relay.subscribe(track), transform="cartoon"
                )
            )
              # Or use MediaRecorder to record
            recorder = MediaBlackhole()
            # recorder = MediaRecorder("sample.mp4")
            recorder.addTrack(VideoTransformTrack(relay.subscribe(track), transform="cartoon"))
            await recorder.start()
            print("Video track added and recorder started")
            @track.on("ended")
            async def on_ended():
                await recorder.stop()

    async for message in websocket.iter_text():
        message = json.loads(message)

        if message["type"] == "offer":
            await handle_offer(websocket, pc, message)
        elif message["type"] == "candidate":
            await handle_candidate(pc, message)
        elif message["type"] == "end_track":
            recorder = MediaBlackhole()
            await handle_end_track(websocket, recorder)

    # Clean up after the connection is closed
    del peer_connections[client_id]
    await pc.close()

# @app.on_event("shutdown")
# async def on_shutdown():
#     # Close all peer connections
#     for pc in peer_connections.values():
#         await pc.close()


@app.get('/live_labels')
def get_live_labels():
    return JSONResponse({"labels" : list(live_labels)})

# Run server
# if __name__ == "__main__":
#     import uvicorn

#     uvicorn.run("app:app", host="0.0.0.0", port=8000, reload="True")
