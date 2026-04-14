# Meridian WebSocket API Documentation

> **Note:** Meridian was previously known as Alex during development. The WebSocket endpoint URLs retain `/alex-chat` for backward compatibility with existing clients.

## Overview

Meridian is the AI guide for the Prism platform. This document provides complete WebSocket API documentation for frontend integration, enabling real-time audio and text conversations with Meridian.

## WebSocket Connection

### Endpoint

```
ws://localhost:8000/v1/agents/ws/alex-chat
```

### Connection Setup

```javascript
const socket = new WebSocket('ws://localhost:8000/v1/agents/ws/alex-chat');

socket.onopen = function(event) {
    console.log('Connected to Meridian');
};

socket.onclose = function(event) {
    console.log('Disconnected from Meridian');
};

socket.onerror = function(error) {
    console.log('WebSocket Error:', error);
};
```

## Message Types

### Outgoing Messages (Client → Server)

#### 1. Text Message

Send a text message to Meridian for processing and response.

```javascript
const textMessage = {
    type: "text",
    text: "Hello Meridian, what is the Prism platform?"
};

socket.send(JSON.stringify(textMessage));
```

#### 2. Real-time Text Message

Send a text message for instant streaming response without processing delays.

```javascript
const realtimeMessage = {
    type: "realtime_text",
    text: "Tell me about the onboarding process"
};

socket.send(JSON.stringify(realtimeMessage));
```

#### 3. Audio Data

Send audio chunks as binary data for voice input.

```javascript
// Send audio chunks (binary data)
socket.send(audioChunk); // ArrayBuffer or Blob

// Signal end of audio input
const audioEndMessage = {
    type: "audio_end"
};

socket.send(JSON.stringify(audioEndMessage));
```

#### 4. Continuous Mode Activation

Activate continuous streaming mode for maximum responsiveness.

```javascript
const continuousMode = {
    type: "start_continuous"
};

socket.send(JSON.stringify(continuousMode));
```

### Incoming Messages (Server → Client)

#### 1. Processing Status

Indicates Meridian is processing the request.

```javascript
{
    type: "processing",
    message: "Processing your audio..." // or "Thinking..."
}
```

#### 2. Transcript

Transcribed text from audio input.

```javascript
{
    type: "transcript",
    text: "Hello Meridian, what is the Prism platform?"
}
```

#### 3. Response Chunk (Streaming)

Partial response text sent in real-time as Meridian generates the response.

```javascript
{
    type: "response_chunk",
    text: "The Prism platform is", // Current chunk
    full_text: "The Prism platform is" // Accumulated response so far
}
```

#### 4. Complete Response

Final complete text response from Meridian.

```javascript
{
    type: "response",
    text: "The Prism platform is an AI-powered onboarding and coaching system..."
}
```

#### 5. Audio Streaming Events

**Audio Start**

```javascript
{
    type: "audio_start",
    format: "pcm" // Audio format
}
```

**Audio Complete**

```javascript
{
    type: "audio_complete"
}
```

#### 6. Continuous Mode Status

Confirmation that continuous mode is active.

```javascript
{
    type: "continuous_mode",
    status: "active",
    message: "Continuous streaming mode activated. I'm ready to respond instantly!"
}
```

#### 7. Error Messages

Error information when something goes wrong.

```javascript
{
    type: "error",
    message: "Error description here"
}
```

#### 8. Binary Audio Data

Audio response chunks sent as binary data for playback.

```javascript
socket.onmessage = function(event) {
    if (event.data instanceof ArrayBuffer) {
        // This is audio data - play it
        playAudioChunk(event.data);
    } else {
        // This is JSON text data
        const message = JSON.parse(event.data);
        handleTextMessage(message);
    }
};
```

## Complete Integration Examples

### Basic Text Chat

```javascript
class MeridianTextChat {
    constructor() {
        this.socket = new WebSocket('ws://localhost:8000/v1/agents/ws/alex-chat');
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.socket.onopen = () => {
            console.log('Connected to Meridian');
        };

        this.socket.onmessage = (event) => {
            if (typeof event.data === 'string') {
                const message = JSON.parse(event.data);
                this.handleMessage(message);
            }
        };
    }

    sendMessage(text) {
        const message = {
            type: "text",
            text: text
        };
        this.socket.send(JSON.stringify(message));
    }

    handleMessage(message) {
        switch (message.type) {
            case 'processing':
                this.showProcessing(message.message);
                break;
            case 'response':
                this.displayResponse(message.text);
                break;
            case 'error':
                this.showError(message.message);
                break;
        }
    }
}
```

### Advanced Audio + Text Chat

```javascript
class MeridianVoiceChat {
    constructor() {
        this.socket = new WebSocket('ws://localhost:8000/v1/agents/ws/alex-chat');
        this.audioContext = new AudioContext();
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.socket.onopen = () => {
            console.log('Connected to Meridian');
            // Activate continuous mode for best performance
            this.socket.send(JSON.stringify({ type: "start_continuous" }));
        };

        this.socket.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
                // Audio data - play it
                this.playAudioChunk(event.data);
            } else {
                // Text data
                const message = JSON.parse(event.data);
                this.handleTextMessage(message);
            }
        };
    }

    // Send text message
    sendText(text, isRealtime = false) {
        const message = {
            type: isRealtime ? "realtime_text" : "text",
            text: text
        };
        this.socket.send(JSON.stringify(message));
    }

    // Start recording audio
    async startRecording() {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.mediaRecorder = new MediaRecorder(stream);
        this.audioChunks = [];

        this.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                // Send audio chunk immediately
                this.socket.send(event.data);
            }
        };

        this.mediaRecorder.start(100); // Send chunks every 100ms
    }

    // Stop recording and process
    stopRecording() {
        if (this.mediaRecorder) {
            this.mediaRecorder.stop();
            // Signal end of audio
            this.socket.send(JSON.stringify({ type: "audio_end" }));
        }
    }

    // Handle text messages
    handleTextMessage(message) {
        switch (message.type) {
            case 'processing':
                this.showProcessingIndicator(message.message);
                break;
            case 'transcript':
                this.displayTranscript(message.text);
                break;
            case 'response_chunk':
                this.updateResponseText(message.text, message.full_text);
                break;
            case 'response':
                this.displayFinalResponse(message.text);
                break;
            case 'audio_start':
                this.prepareAudioPlayback();
                break;
            case 'audio_complete':
                this.finishAudioPlayback();
                break;
            case 'continuous_mode':
                this.showContinuousModeActive();
                break;
            case 'error':
                this.handleError(message.message);
                break;
        }
    }

    // Play audio chunks
    async playAudioChunk(audioData) {
        try {
            const audioBuffer = await this.audioContext.decodeAudioData(audioData);
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);
            source.start();
        } catch (error) {
            console.error('Error playing audio:', error);
        }
    }
}
```

### Real-time Streaming Chat

```javascript
class MeridianStreamingChat {
    constructor() {
        this.socket = new WebSocket('ws://localhost:8000/v1/agents/ws/alex-chat');
        this.currentResponse = '';
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.socket.onopen = () => {
            // Activate continuous mode for instant responses
            this.socket.send(JSON.stringify({ type: "start_continuous" }));
        };

        this.socket.onmessage = (event) => {
            if (typeof event.data === 'string') {
                const message = JSON.parse(event.data);
                this.handleStreamingMessage(message);
            } else {
                // Handle audio data
                this.handleAudioData(event.data);
            }
        };
    }

    // Send message with instant streaming
    sendInstantMessage(text) {
        this.currentResponse = '';
        const message = {
            type: "realtime_text",
            text: text
        };
        this.socket.send(JSON.stringify(message));
    }

    handleStreamingMessage(message) {
        switch (message.type) {
            case 'response_chunk':
                // Update response in real-time
                this.currentResponse = message.full_text;
                this.updateResponseDisplay(this.currentResponse);
                break;
            case 'response':
                // Final response
                this.finalizeResponse(message.text);
                break;
            case 'audio_start':
                this.startAudioPlayback();
                break;
            case 'audio_complete':
                this.stopAudioPlayback();
                break;
        }
    }
}
```

## Audio Handling

### Recording Audio

```javascript
// Start recording
async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
            sampleRate: 16000,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true
        }
    });
  
    const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm'
    });
  
    mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
            socket.send(event.data);
        }
    };
  
    mediaRecorder.start(250); // Send chunks every 250ms
    return mediaRecorder;
}
```

### Playing Audio Response

```javascript
// Play audio chunks as they arrive
async function playAudioChunk(audioArrayBuffer) {
    const audioContext = new AudioContext();
  
    try {
        const audioBuffer = await audioContext.decodeAudioData(audioArrayBuffer);
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        source.start();
    } catch (error) {
        console.error('Audio playback error:', error);
    }
}
```

## Message Flow Examples

### Text Chat Flow

```
1. Client → Server: {"type": "text", "text": "What is Prism?"}
2. Server → Client: {"type": "processing", "message": "Thinking..."}
3. Server → Client: {"type": "response_chunk", "text": "Prism is", "full_text": "Prism is"}
4. Server → Client: {"type": "response_chunk", "text": " an AI-powered", "full_text": "Prism is an AI-powered"}
5. Server → Client: {"type": "response", "text": "Prism is an AI-powered platform..."}
6. Server → Client: {"type": "audio_start", "format": "pcm"}
7. Server → Client: [Binary audio data chunks...]
8. Server → Client: {"type": "audio_complete"}
```

### Voice Chat Flow

```
1. Client → Server: [Binary audio chunks...]
2. Client → Server: {"type": "audio_end"}
3. Server → Client: {"type": "processing", "message": "Processing your audio..."}
4. Server → Client: {"type": "transcript", "text": "What is Prism?"}
5. Server → Client: {"type": "response_chunk", "text": "Prism is", "full_text": "Prism is"}
6. Server → Client: {"type": "audio_start", "format": "pcm"}
7. Server → Client: [Binary audio data chunks...]
8. Server → Client: {"type": "response", "text": "Complete response..."}
9. Server → Client: {"type": "audio_complete"}
```

## Error Handling

### Connection Errors

```javascript
socket.onerror = function(error) {
    console.error('WebSocket error:', error);
    // Implement reconnection logic
    setTimeout(() => {
        connectToMeridian();
    }, 3000);
};

socket.onclose = function(event) {
    if (event.code !== 1000) {
        // Unexpected close - attempt reconnection
        setTimeout(() => {
            connectToMeridian();
        }, 2000);
    }
};
```

### Message Errors

```javascript
// Handle error messages from server
if (message.type === 'error') {
    console.error('Meridian error:', message.message);
    // Show user-friendly error message
    showErrorToUser('Meridian encountered an error. Please try again.');
}
```

## Performance Optimization

### Buffering Audio

```javascript
class AudioBuffer {
    constructor() {
        this.chunks = [];
        this.isPlaying = false;
    }

    addChunk(audioData) {
        this.chunks.push(audioData);
        if (!this.isPlaying) {
            this.playNext();
        }
    }

    async playNext() {
        if (this.chunks.length === 0) {
            this.isPlaying = false;
            return;
        }

        this.isPlaying = true;
        const chunk = this.chunks.shift();
        await this.playChunk(chunk);
        this.playNext();
    }
}
```

### Optimizing Message Handling

```javascript
// Throttle response chunk updates to prevent UI flickering
const throttledUpdateResponse = throttle((text) => {
    updateResponseDisplay(text);
}, 50); // Update every 50ms max

// Handle response chunks
if (message.type === 'response_chunk') {
    throttledUpdateResponse(message.full_text);
}
```

## Best Practices

1. **Always handle both text and binary messages** in your WebSocket handler
2. **Use continuous mode** for the most responsive experience
3. **Buffer audio chunks** for smooth playback
4. **Implement reconnection logic** for connection drops
5. **Show processing indicators** to improve user experience
6. **Handle errors gracefully** with user-friendly messages
7. **Use real-time text mode** for instant responses when possible
8. **Optimize audio settings** for best quality and performance

This documentation provides everything needed to integrate Meridian's AI chat functionality into your frontend application with full audio and text support.
