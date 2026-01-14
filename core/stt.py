"""
Speech-to-Text with Wake Word Detection for Voice Assistant.
Supports both Whisper and Vosk backends.
"""

import threading
import queue
import time
import numpy as np
import sounddevice as sd
from typing import Optional, Callable
from config import (
    STT_MODEL_PATH, STT_USE_WHISPER, WHISPER_MODEL_SIZE, WAKE_WORD, WAKE_WORD_SENSITIVITY,
    STT_SAMPLE_RATE, STT_CHUNK_SIZE, STT_RECORD_TIMEOUT, USE_PORCUPINE_WAKE_WORD,
    PORCUPINE_ACCESS_KEY, GRAY, RESET, CYAN, YELLOW
)


class PorcupineWakeWordDetector:
    """Porcupine-based wake word detector (more accurate)."""
    
    def __init__(self, access_key: Optional[str] = None):
        self.access_key = access_key
        self.porcupine = None
        self.initialized = False
        
    def initialize(self) -> bool:
        """Initialize Porcupine."""
        try:
            import pvporcupine
            if not self.access_key:
                print(f"{YELLOW}[WakeWord] Porcupine access key not provided. Get one from https://console.picovoice.ai/{RESET}")
                return False
            
            print(f"{CYAN}[WakeWord] Initializing Porcupine wake word detector...{RESET}")
            # Create custom keyword - "ada" (case-insensitive)
            # Porcupine requires keyword files, but we can use built-in keywords or create custom
            # For now, we'll use a similar-sounding built-in keyword or create custom
            # Note: Custom keywords require training, so we'll use a workaround
            self.porcupine = pvporcupine.create(
                access_key=self.access_key,
                keywords=["hey siri"]  # Placeholder - would need custom keyword for "ada"
            )
            self.initialized = True
            print(f"{CYAN}[WakeWord] ✓ Porcupine initialized{RESET}")
            return True
        except ImportError:
            print(f"{GRAY}[WakeWord] Porcupine not installed. Install with: pip install pvporcupine{RESET}")
            return False
        except Exception as e:
            print(f"{GRAY}[WakeWord] Porcupine initialization error: {e}{RESET}")
            return False
    
    def process(self, audio_frame: np.ndarray) -> bool:
        """Process audio frame and return True if wake word detected."""
        if not self.initialized or not self.porcupine:
            return False
        
        try:
            keyword_index = self.porcupine.process(audio_frame)
            return keyword_index >= 0
        except Exception as e:
            print(f"{GRAY}[WakeWord] Porcupine processing error: {e}{RESET}")
            return False
    
    def cleanup(self):
        """Clean up Porcupine resources."""
        if self.porcupine:
            self.porcupine.delete()
            self.porcupine = None


class WakeWordDetector:
    """Detects wake word 'Ada' in audio stream using transcription."""
    
    def __init__(self, sensitivity: float = 0.5):
        self.sensitivity = sensitivity
        self.wake_word = WAKE_WORD.lower()
        self.detected = False
        
    def check_audio(self, text: str) -> bool:
        """Check if wake word is in transcribed text."""
        if not text:
            return False
        
        text_lower = text.lower()
        # DEBUG: Print all transcribed text for wake word detection
        print(f"{GRAY}[WakeWord] Checking text: '{text_lower}' (looking for '{self.wake_word}'){RESET}")
        
        # More flexible matching - check for variations
        # Check for exact word match
        words = text_lower.split()
        if self.wake_word in words:
            self.detected = True
            print(f"{GREEN}[WakeWord] ✓ WAKE WORD DETECTED in: '{text_lower}'{RESET}")
            return True
        
        # Also check if wake word appears as substring (more lenient)
        if self.wake_word in text_lower:
            # Check if it's at word boundaries or standalone
            import re
            pattern = r'\b' + re.escape(self.wake_word) + r'\b'
            if re.search(pattern, text_lower):
                self.detected = True
                print(f"{GREEN}[WakeWord] ✓ WAKE WORD DETECTED (substring match) in: '{text_lower}'{RESET}")
                return True
            else:
                print(f"{GRAY}[WakeWord] '{self.wake_word}' found but not at word boundary{RESET}")
        
        return False


class SpeechRecognizer:
    """Speech-to-text recognition using Whisper or Vosk."""
    
    def __init__(self, use_whisper: bool = True, model_path: Optional[str] = None):
        self.use_whisper = use_whisper
        self.model_path = model_path
        self.model = None
        self.recognizer = None
        self.initialized = False
        
    def initialize(self) -> bool:
        """Initialize the STT model."""
        try:
            if self.use_whisper:
                return self._init_whisper()
            else:
                return self._init_vosk()
        except Exception as e:
            print(f"{GRAY}[STT] Failed to initialize: {e}{RESET}")
            return False
    
    def _init_whisper(self) -> bool:
        """Initialize Whisper model."""
        try:
            import whisper
            model_size = WHISPER_MODEL_SIZE
            print(f"{CYAN}[STT] Loading Whisper model ({model_size})...{RESET}")
            print(f"{CYAN}[STT] Model sizes: tiny (fastest), base, small (recommended), medium, large (most accurate){RESET}")
            print(f"{CYAN}[STT] This may take a moment on first run (model will be downloaded if needed)...{RESET}")
            
            # Use configured model size (small recommended for good accuracy/speed balance)
            self.model = whisper.load_model(model_size)
            self.initialized = True
            print(f"{CYAN}[STT] ✓ Whisper model ({model_size}) loaded successfully{RESET}")
            print(f"{CYAN}[STT]   For better accuracy, you can use 'medium' or 'large' in config.py{RESET}")
            return True
        except ImportError:
            print(f"{GRAY}[STT] ✗ Whisper not installed. Install with: pip install openai-whisper{RESET}")
            return False
        except Exception as e:
            print(f"{GRAY}[STT] ✗ Whisper initialization error: {e}{RESET}")
            import traceback
            traceback.print_exc()
            return False
    
    def _init_vosk(self) -> bool:
        """Initialize Vosk model."""
        try:
            import vosk
            if not self.model_path:
                print(f"{GRAY}[STT] Vosk model path not specified in config.{RESET}")
                return False
            
            print(f"{CYAN}[STT] Loading Vosk model from {self.model_path}...{RESET}")
            self.model = vosk.Model(self.model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, STT_SAMPLE_RATE)
            self.recognizer.SetWords(True)
            self.initialized = True
            print(f"{CYAN}[STT] Vosk model loaded.{RESET}")
            return True
        except ImportError:
            print(f"{GRAY}[STT] Vosk not installed. Install with: pip install vosk{RESET}")
            return False
        except Exception as e:
            print(f"{GRAY}[STT] Vosk initialization error: {e}{RESET}")
            return False
    
    def transcribe(self, audio_data: np.ndarray) -> str:
        """Transcribe audio data to text."""
        if not self.initialized:
            return ""
        
        try:
            if self.use_whisper:
                return self._transcribe_whisper(audio_data)
            else:
                return self._transcribe_vosk(audio_data)
        except Exception as e:
            print(f"{GRAY}[STT] Transcription error: {e}{RESET}")
            return ""
    
    def _transcribe_whisper(self, audio_data: np.ndarray) -> str:
        """Transcribe using Whisper."""
        print(f"{GRAY}[STT] Transcribing with Whisper (audio shape: {audio_data.shape}, dtype: {audio_data.dtype})...{RESET}")
        # Whisper expects float32 audio in range [-1, 1]
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)
        
        # Normalize if needed
        if audio_data.max() > 1.0 or audio_data.min() < -1.0:
            audio_data = audio_data / 32768.0 if audio_data.dtype == np.int16 else audio_data
        
        try:
            result = self.model.transcribe(audio_data, language="en", fp16=False)
            text = result["text"].strip()
            print(f"{GRAY}[STT] Whisper transcription result: '{text}'{RESET}")
            return text
        except Exception as e:
            print(f"{GRAY}[STT] Whisper transcription error: {e}{RESET}")
            return ""
    
    def _transcribe_vosk(self, audio_data: np.ndarray) -> str:
        """Transcribe using Vosk."""
        # Vosk expects int16 audio
        if audio_data.dtype != np.int16:
            audio_data = (audio_data * 32768).astype(np.int16)
        
        text = ""
        audio_bytes = audio_data.tobytes()
        
        # Process in chunks
        chunk_size = 4000
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            if self.recognizer.AcceptWaveform(chunk):
                result = self.recognizer.Result()
                import json
                result_dict = json.loads(result)
                if "text" in result_dict:
                    text += result_dict["text"] + " "
        
        # Get final result
        final_result = self.recognizer.FinalResult()
        import json
        final_dict = json.loads(final_result)
        if "text" in final_dict:
            text += final_dict["text"]
        
        return text.strip()


class STTListener:
    """Continuous microphone listener with wake word detection."""
    
    def __init__(self, 
                 wake_word_callback: Callable[[], None],
                 speech_callback: Callable[[str], None]):
        self.wake_word_callback = wake_word_callback
        self.speech_callback = speech_callback
        self.running = False
        self.listening_thread = None
        
        # Choose wake word detector
        if USE_PORCUPINE_WAKE_WORD and PORCUPINE_ACCESS_KEY:
            self.porcupine_detector = PorcupineWakeWordDetector(PORCUPINE_ACCESS_KEY)
            self.wake_detector = None
            print(f"{CYAN}[STT] Using Porcupine for wake word detection{RESET}")
        else:
            self.porcupine_detector = None
            self.wake_detector = WakeWordDetector(WAKE_WORD_SENSITIVITY)
            print(f"{CYAN}[STT] Using transcription-based wake word detection{RESET}")
        
        self.recognizer = SpeechRecognizer(STT_USE_WHISPER, STT_MODEL_PATH)
        self.audio_queue = queue.Queue()
        self.current_audio = []
        self.is_listening_for_speech = False
        self.silence_threshold = 0.01
        self.silence_duration = 1.0  # seconds of silence before stopping
        self.last_sound_time = None
        
    def initialize(self) -> bool:
        """Initialize STT models."""
        # Initialize Porcupine if using it
        if self.porcupine_detector:
            if not self.porcupine_detector.initialize():
                print(f"{YELLOW}[STT] Porcupine initialization failed, falling back to transcription-based detection{RESET}")
                self.porcupine_detector = None
                self.wake_detector = WakeWordDetector(WAKE_WORD_SENSITIVITY)
        
        return self.recognizer.initialize()
    
    def start(self):
        """Start continuous listening."""
        if self.running:
            print(f"{GRAY}[STT] Already running.{RESET}")
            return
        
        if not self.recognizer.initialized:
            print(f"{GRAY}[STT] Recognizer not initialized, attempting initialization...{RESET}")
            if not self.initialize():
                print(f"{GRAY}[STT] Failed to initialize, cannot start listening.{RESET}")
                return
        
        self.running = True
        self.listening_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listening_thread.start()
        print(f"{CYAN}[STT] ✓ Started listening for wake word '{WAKE_WORD}'...{RESET}")
        print(f"{CYAN}[STT]   Sample rate: {STT_SAMPLE_RATE}Hz, Chunk size: {STT_CHUNK_SIZE}{RESET}")
        print(f"{CYAN}[STT]   Using: {'Whisper' if STT_USE_WHISPER else 'Vosk'}{RESET}")
    
    def stop(self):
        """Stop listening."""
        self.running = False
        if self.listening_thread:
            self.listening_thread.join(timeout=2.0)
        print(f"{GRAY}[STT] Stopped listening.{RESET}")
    
    def _listen_loop(self):
        """Main listening loop."""
        try:
            print(f"{CYAN}[STT] Opening audio input stream...{RESET}")
            with sd.InputStream(
                samplerate=STT_SAMPLE_RATE,
                channels=1,
                dtype='float32',
                blocksize=STT_CHUNK_SIZE,
                callback=self._audio_callback
            ):
                print(f"{CYAN}[STT] ✓ Audio stream opened successfully{RESET}")
                print(f"{CYAN}[STT] Listening loop started. Say '{WAKE_WORD}' to activate...{RESET}")
                while self.running:
                    time.sleep(0.1)
                    
                    # Process audio queue
                    if not self.audio_queue.empty():
                        audio_chunk = self.audio_queue.get()
                        
                        if not self.is_listening_for_speech:
                            # Check for wake word
                            self._check_wake_word(audio_chunk)
                        else:
                            # Collect speech after wake word
                            self._collect_speech(audio_chunk)
        except Exception as e:
            print(f"{GRAY}[STT] ✗ Listening error: {e}{RESET}")
            import traceback
            traceback.print_exc()
            self.running = False
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback for audio input."""
        if status:
            print(f"{GRAY}[STT] Audio status: {status}{RESET}")
        
        if self.running:
            # Convert to numpy array
            audio_chunk = indata[:, 0].copy()
            # DEBUG: Check audio level
            audio_level = np.abs(audio_chunk).mean()
            if audio_level > 0.01:  # Only log if there's significant audio
                print(f"{GRAY}[STT] Audio captured: level={audio_level:.4f}, frames={frames}{RESET}")
            self.audio_queue.put(audio_chunk)
    
    def _check_wake_word(self, audio_chunk: np.ndarray):
        """Check if wake word is present in audio chunk."""
        # If using Porcupine, check directly on audio
        if self.porcupine_detector and self.porcupine_detector.initialized:
            # Convert to int16 for Porcupine (expects 16-bit PCM)
            if audio_chunk.dtype != np.int16:
                audio_int16 = (audio_chunk * 32768).astype(np.int16)
            else:
                audio_int16 = audio_chunk
            
            # Porcupine expects specific frame length
            porcupine_frame_length = self.porcupine_detector.porcupine.frame_length
            if len(audio_int16) >= porcupine_frame_length:
                # Process frame
                frame = audio_int16[:porcupine_frame_length]
                if self.porcupine_detector.process(frame):
                    print(f"{CYAN}[STT] ✓ Wake word '{WAKE_WORD}' detected via Porcupine!{RESET}")
                    self.is_listening_for_speech = True
                    self.current_audio = []
                    self.last_sound_time = time.time()
                    self.wake_word_callback()
            return
        
        # Transcription-based detection (fallback or default)
        # Buffer audio for wake word detection
        self.current_audio.append(audio_chunk)
        
        # Keep buffer size reasonable (last 3 seconds)
        max_buffer_size = int(STT_SAMPLE_RATE * 3 / STT_CHUNK_SIZE)
        if len(self.current_audio) > max_buffer_size:
            self.current_audio.pop(0)
        
        # Periodically check for wake word (every ~1 second of audio)
        chunks_needed = int(STT_SAMPLE_RATE / STT_CHUNK_SIZE)
        if len(self.current_audio) >= chunks_needed:
            # Concatenate audio
            audio_buffer = np.concatenate(self.current_audio[-chunks_needed:])
            
            # DEBUG: Log transcription attempt
            print(f"{GRAY}[STT] Attempting wake word transcription (buffer size: {len(audio_buffer)} samples)...{RESET}")
            
            # Quick transcription for wake word detection
            # Use shorter chunks for faster detection
            try:
                text = self.recognizer.transcribe(audio_buffer)
                print(f"{GRAY}[STT] Transcribed text: '{text}'{RESET}")
            except Exception as e:
                print(f"{GRAY}[STT] Transcription error: {e}{RESET}")
                return
            
            if self.wake_detector.check_audio(text):
                print(f"{CYAN}[STT] ✓ Wake word '{WAKE_WORD}' detected! Switching to speech mode...{RESET}")
                self.is_listening_for_speech = True
                self.current_audio = []  # Clear buffer
                self.last_sound_time = time.time()
                print(f"{CYAN}[STT] Calling wake_word_callback...{RESET}")
                self.wake_word_callback()
            else:
                print(f"{GRAY}[STT] No wake word found in: '{text}'{RESET}")
    
    def _collect_speech(self, audio_chunk: np.ndarray):
        """Collect speech after wake word detection."""
        self.current_audio.append(audio_chunk)
        
        # Check for silence (end of speech)
        audio_level = np.abs(audio_chunk).mean()
        current_time = time.time()
        
        if audio_level > self.silence_threshold:
            self.last_sound_time = current_time
        
        # Stop if silence detected or timeout reached
        elapsed = current_time - (self.last_sound_time or current_time)
        total_duration = len(self.current_audio) * STT_CHUNK_SIZE / STT_SAMPLE_RATE
        
        if elapsed > self.silence_duration or total_duration > STT_RECORD_TIMEOUT:
            # Process collected speech
            if len(self.current_audio) > 0:
                audio_buffer = np.concatenate(self.current_audio)
                text = self.recognizer.transcribe(audio_buffer)
                
                if text.strip():
                    print(f"{CYAN}[STT] Recognized: {text}{RESET}")
                    self.speech_callback(text)
            
            # Reset for next wake word
            self.is_listening_for_speech = False
            self.current_audio = []
            self.last_sound_time = None
