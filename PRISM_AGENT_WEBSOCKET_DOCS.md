# Prism Agent WebSocket API Documentation

## Overview

The Prism Agent WebSocket API provides real-time communication with AI agents within the Prism platform. This document provides complete WebSocket API documentation for frontend integration, enabling authenticated users to have real-time audio and text conversations with specific AI agents.

## WebSocket Connection

### Endpoint

```
ws://localhost:8000/v1/agents/ws/prism-agent/{agent_id}
```

### Authentication Required

Unlike the Alex chat endpoint, the Prism Agent WebSocket requires authentication. You must provide a valid access token during the initialization phase.

### Connection Setup

```javascript
const agentId = 'your-agent-id-here';
const socket = new WebSocket(`ws://localhost:8000/v1/agents/ws/prism-agent/${agentId}`);

socket.onopen = function(event) {
    console.log('Connected to Prism Agent');
    
    // REQUIRED: Send initialization message with authentication
    const initMessage = {
        type: "init",
        access_token: "your-jwt-access-token-here",
        file_ids: ["file1", "file2", "file3"] // Optional file IDs
    };
    
    socket.send(JSON.stringify(initMessage));
};

socket.onclose = function(event) {
    console.log('Disconnected from Prism Agent');
};

socket.onerror = function(error) {
    console.log('WebSocket Error:', error);
};
```

## Authentication Flow

### Initial Connection

Upon connection, you **must** immediately send an initialization message with your access token:

```javascript
const initMessage = {
    type: "init",
    access_token: "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...", // Your JWT token
    file_ids: ["file1", "file2", "file3"] // Optional array of file IDs
};

socket.send(JSON.stringify(initMessage));
```

### Authentication Responses

**Success Response:**
```javascript
{
    type: "init_success",
    message: "Prism agent {agent_id} initialized successfully",
    user_id: "authenticated-user-uuid"
}
```

**Authentication Error:**
```javascript
{
    type: "auth_error",
    message: "Access token is required" // or "Authentication failed: {error details}"
}
```

**Initialization Error:**
```javascript
{
    type: "init_error",
    message: "Expected init message with access_token and file_ids"
}
```

## Message Types

### Outgoing Messages (Client → Server)

#### 1. Initialization Message (Required First)

Must be sent immediately after connection to authenticate and initialize the agent.

```javascript
const initMessage = {
    type: "init",
    access_token: "your-jwt-access-token",
    file_ids: ["file1", "file2", "file3"] // Optional
};

socket.send(JSON.stringify(initMessage));
```

#### 2. Text Message

Send a text message to the agent for processing and response.

```javascript
const textMessage = {
    type: "text",
    text: "Hello, can you help me with my project?"
};

socket.send(JSON.stringify(textMessage));
```

#### 3. Real-time Text Message

Send a text message for instant streaming response without processing delays.

```javascript
const realtimeMessage = {
    type: "realtime_text",
    text: "Tell me about the project requirements"
};

socket.send(JSON.stringify(realtimeMessage));
```

#### 4. Audio Data

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

#### 5. Continuous Mode Activation

Activate continuous streaming mode for maximum responsiveness.

```javascript
const continuousMode = {
    type: "start_continuous"
};

socket.send(JSON.stringify(continuousMode));
```

### Incoming Messages (Server → Client)

#### 1. Authentication Messages

**Initialization Success:**
```javascript
{
    type: "init_success",
    message: "Prism agent {agent_id} initialized successfully",
    user_id: "user-uuid"
}
```

**Authentication Error:**
```javascript
{
    type: "auth_error",
    message: "Authentication failed: Token verification failed"
}
```

**Initialization Error:**
```javascript
{
    type: "init_error",
    message: "Expected init message with access_token and file_ids"
}
```

#### 2. Processing Status

Indicates the agent is processing the request.

```javascript
{
    type: "processing",
    message: "Processing your audio..." // or "Thinking..."
}
```

#### 3. Transcript

Transcribed text from audio input.

```javascript
{
    type: "transcript",
    text: "Hello, can you help me with my project?"
}
```

#### 4. Response Chunk (Streaming)

Partial response text sent in real-time as the agent generates the response.

```javascript
{
    type: "response_chunk",
    text: "I'd be happy to", // Current chunk
    full_text: "I'd be happy to" // Accumulated response so far
}
```

#### 5. Complete Response

Final complete text response from the agent.

```javascript
{
    type: "response",
    text: "I'd be happy to help you with your project. Can you tell me more about what you're working on?"
}
```

#### 6. Audio Streaming Events

**Audio Start:**
```javascript
{
    type: "audio_start",
    format: "pcm" // Audio format
}
```

**Audio Complete:**
```javascript
{
    type: "audio_complete"
}
```

#### 7. Continuous Mode Status

Confirmation that continuous mode is active.

```javascript
{
    type: "continuous_mode",
    status: "active",
    message: "Continuous streaming mode activated for agent {agent_id}. I'm ready to respond instantly!"
}
```

#### 8. Error Messages

Error information when something goes wrong.

```javascript
{
    type: "error",
    message: "Error description here"
}
```

#### 9. Binary Audio Data

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

### Basic Authenticated Text Chat

```javascript
class PrismAgentTextChat {
    constructor(agentId, accessToken) {
        this.agentId = agentId;
        this.accessToken = accessToken;
        this.socket = new WebSocket(`ws://localhost:8000/v1/agents/ws/prism-agent/${agentId}`);
        this.isAuthenticated = false;
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.socket.onopen = () => {
            console.log('Connected to Prism Agent');
            this.authenticate();
        };

        this.socket.onmessage = (event) => {
            if (typeof event.data === 'string') {
                const message = JSON.parse(event.data);
                this.handleMessage(message);
            }
        };

        this.socket.onclose = () => {
            console.log('Disconnected from Prism Agent');
        };
    }

    authenticate() {
        const initMessage = {
            type: "init",
            access_token: this.accessToken,
            file_ids: [] // Optional
        };
        this.socket.send(JSON.stringify(initMessage));
    }

    sendMessage(text) {
        if (!this.isAuthenticated) {
            console.error('Not authenticated yet');
            return;
        }

        const message = {
            type: "text",
            text: text
        };
        this.socket.send(JSON.stringify(message));
    }

    handleMessage(message) {
        switch (message.type) {
            case 'init_success':
                this.isAuthenticated = true;
                this.onAuthenticated(message.user_id);
                break;
            case 'auth_error':
                this.onAuthError(message.message);
                break;
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

    onAuthenticated(userId) {
        console.log(`Authenticated as user: ${userId}`);
        // Now you can send messages
    }

    onAuthError(error) {
        console.error(`Authentication failed: ${error}`);
        // Handle authentication failure
    }
}

// Usage
const agentChat = new PrismAgentTextChat('agent-123', 'your-jwt-token');
```

### Advanced Audio + Text Chat with Authentication

```javascript
class PrismAgentVoiceChat {
    constructor(agentId, accessToken, fileIds = []) {
        this.agentId = agentId;
        this.accessToken = accessToken;
        this.fileIds = fileIds;
        this.socket = new WebSocket(`ws://localhost:8000/v1/agents/ws/prism-agent/${agentId}`);
        this.audioContext = new AudioContext();
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isAuthenticated = false;
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.socket.onopen = () => {
            console.log('Connected to Prism Agent');
            this.authenticate();
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

    authenticate() {
        const initMessage = {
            type: "init",
            access_token: this.accessToken,
            file_ids: this.fileIds
        };
        this.socket.send(JSON.stringify(initMessage));
    }

    // Send text message
    sendText(text, isRealtime = false) {
        if (!this.isAuthenticated) {
            console.error('Not authenticated yet');
            return;
        }

        const message = {
            type: isRealtime ? "realtime_text" : "text",
            text: text
        };
        this.socket.send(JSON.stringify(message));
    }

    // Start recording audio
    async startRecording() {
        if (!this.isAuthenticated) {
            console.error('Not authenticated yet');
            return;
        }

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
            case 'init_success':
                this.isAuthenticated = true;
                this.onAuthenticated(message.user_id);
                // Activate continuous mode for best performance
                this.socket.send(JSON.stringify({ type: "start_continuous" }));
                break;
            case 'auth_error':
                this.onAuthError(message.message);
                break;
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

    onAuthenticated(userId) {
        console.log(`Authenticated as user: ${userId} for agent: ${this.agentId}`);
        // Now you can send messages and start recording
    }

    onAuthError(error) {
        console.error(`Authentication failed: ${error}`);
        // Handle authentication failure - maybe redirect to login
    }
}

// Usage
const agentVoiceChat = new PrismAgentVoiceChat(
    'agent-123', 
    'your-jwt-token',
    ['file1', 'file2', 'file3']
);
```

### Real-time Streaming Chat with File Context

```javascript
class PrismAgentStreamingChat {
    constructor(agentId, accessToken, fileIds = []) {
        this.agentId = agentId;
        this.accessToken = accessToken;
        this.fileIds = fileIds;
        this.socket = new WebSocket(`ws://localhost:8000/v1/agents/ws/prism-agent/${agentId}`);
        this.currentResponse = '';
        this.isAuthenticated = false;
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.socket.onopen = () => {
            this.authenticate();
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

    authenticate() {
        const initMessage = {
            type: "init",
            access_token: this.accessToken,
            file_ids: this.fileIds
        };
        this.socket.send(JSON.stringify(initMessage));
    }

    // Send message with instant streaming
    sendInstantMessage(text) {
        if (!this.isAuthenticated) {
            console.error('Not authenticated yet');
            return;
        }

        this.currentResponse = '';
        const message = {
            type: "realtime_text",
            text: text
        };
        this.socket.send(JSON.stringify(message));
    }

    handleStreamingMessage(message) {
        switch (message.type) {
            case 'init_success':
                this.isAuthenticated = true;
                this.onAuthenticated(message.user_id);
                // Activate continuous mode for instant responses
                this.socket.send(JSON.stringify({ type: "start_continuous" }));
                break;
            case 'auth_error':
                this.onAuthError(message.message);
                break;
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

    onAuthenticated(userId) {
        console.log(`Authenticated streaming chat for user: ${userId}, agent: ${this.agentId}`);
        console.log(`Using file context: ${this.fileIds.join(', ')}`);
    }

    onAuthError(error) {
        console.error(`Authentication failed: ${error}`);
        // Handle authentication failure
    }
}

// Usage with file context
const streamingChat = new PrismAgentStreamingChat(
    'my-coding-agent',
    'your-jwt-token',
    ['project-requirements.pdf', 'codebase-overview.md', 'user-stories.doc']
);
```

## Authentication Best Practices

### Token Management

```javascript
class TokenManager {
    constructor() {
        this.accessToken = null;
        this.refreshToken = null;
        this.tokenExpiry = null;
    }

    async getValidToken() {
        if (this.isTokenExpired()) {
            await this.refreshAccessToken();
        }
        return this.accessToken;
    }

    isTokenExpired() {
        return !this.tokenExpiry || Date.now() >= this.tokenExpiry;
    }

    async refreshAccessToken() {
        // Implement token refresh logic
        // This depends on your authentication system
    }
}

// Usage with token management
const tokenManager = new TokenManager();

async function createAgentConnection(agentId) {
    const token = await tokenManager.getValidToken();
    return new PrismAgentVoiceChat(agentId, token);
}
```

### Error Handling

```javascript
class PrismAgentWithErrorHandling extends PrismAgentTextChat {
    constructor(agentId, accessToken) {
        super(agentId, accessToken);
        this.maxRetries = 3;
        this.retryCount = 0;
    }

    handleMessage(message) {
        switch (message.type) {
            case 'auth_error':
                this.handleAuthError(message.message);
                break;
            case 'init_error':
                this.handleInitError(message.message);
                break;
            default:
                super.handleMessage(message);
        }
    }

    handleAuthError(error) {
        console.error(`Authentication error: ${error}`);
        
        if (this.retryCount < this.maxRetries) {
            this.retryCount++;
            console.log(`Retrying authentication (${this.retryCount}/${this.maxRetries})`);
            
            // Try to refresh token and reconnect
            this.refreshTokenAndReconnect();
        } else {
            console.error('Max authentication retries reached');
            this.onAuthenticationFailed();
        }
    }

    handleInitError(error) {
        console.error(`Initialization error: ${error}`);
        // Handle initialization errors
        this.onInitializationFailed(error);
    }

    async refreshTokenAndReconnect() {
        try {
            // Refresh token logic here
            const newToken = await this.refreshToken();
            this.accessToken = newToken;
            
            // Reconnect
            this.socket.close();
            this.socket = new WebSocket(`ws://localhost:8000/v1/agents/ws/prism-agent/${this.agentId}`);
            this.setupEventListeners();
        } catch (error) {
            console.error('Token refresh failed:', error);
            this.onAuthenticationFailed();
        }
    }

    onAuthenticationFailed() {
        // Redirect to login page or show error message
        console.error('Authentication failed completely');
        // window.location.href = '/login';
    }

    onInitializationFailed(error) {
        // Handle initialization failure
        console.error('Agent initialization failed:', error);
    }
}
```

## Message Flow Examples

### Authenticated Text Chat Flow

```
1. Client → Server: Connection established
2. Client → Server: {"type": "init", "access_token": "jwt-token", "file_ids": ["file1"]}
3. Server → Client: {"type": "init_success", "message": "Agent initialized", "user_id": "user-123"}
4. Client → Server: {"type": "text", "text": "Hello agent"}
5. Server → Client: {"type": "processing", "message": "Thinking..."}
6. Server → Client: {"type": "response_chunk", "text": "Hello!", "full_text": "Hello!"}
7. Server → Client: {"type": "response", "text": "Hello! How can I help you today?"}
8. Server → Client: {"type": "audio_start", "format": "pcm"}
9. Server → Client: [Binary audio data chunks...]
10. Server → Client: {"type": "audio_complete"}
```

### Authentication Failure Flow

```
1. Client → Server: Connection established
2. Client → Server: {"type": "init", "access_token": "invalid-token", "file_ids": []}
3. Server → Client: {"type": "auth_error", "message": "Authentication failed: Token verification failed"}
4. Server → Client: Connection closed
```

### Voice Chat Flow

```
1. Client → Server: Connection established
2. Client → Server: {"type": "init", "access_token": "valid-token", "file_ids": ["doc1"]}
3. Server → Client: {"type": "init_success", "message": "Agent initialized", "user_id": "user-123"}
4. Client → Server: {"type": "start_continuous"}
5. Server → Client: {"type": "continuous_mode", "status": "active", "message": "Continuous mode activated"}
6. Client → Server: [Binary audio chunks...]
7. Client → Server: {"type": "audio_end"}
8. Server → Client: {"type": "processing", "message": "Processing your audio..."}
9. Server → Client: {"type": "transcript", "text": "What files are available?"}
10. Server → Client: {"type": "response_chunk", "text": "Based on", "full_text": "Based on"}
11. Server → Client: {"type": "audio_start", "format": "pcm"}
12. Server → Client: [Binary audio data chunks...]
13. Server → Client: {"type": "response", "text": "Based on the document you provided..."}
14. Server → Client: {"type": "audio_complete"}
```

## Security Considerations

### Token Security

1. **Never log tokens** in client-side console or server logs
2. **Use HTTPS/WSS** in production environments
3. **Implement token refresh** to minimize exposure time
4. **Validate tokens** on every WebSocket connection

### Connection Security

```javascript
// Use secure WebSocket in production
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const socket = new WebSocket(`${protocol}//your-domain.com/v1/agents/ws/prism-agent/${agentId}`);

// Implement connection timeout
const connectionTimeout = setTimeout(() => {
    if (socket.readyState !== WebSocket.OPEN) {
        socket.close();
        console.error('Connection timeout');
    }
}, 10000); // 10 seconds

socket.onopen = () => {
    clearTimeout(connectionTimeout);
    // Proceed with authentication
};
```

### File ID Security

```javascript
// Validate file IDs before sending
function validateFileIds(fileIds) {
    return fileIds.filter(id => {
        // Implement your file ID validation logic
        return typeof id === 'string' && id.length > 0 && id.length < 100;
    });
}

const validFileIds = validateFileIds(userProvidedFileIds);
```

## Performance Optimization

### Connection Pooling

```javascript
class PrismAgentConnectionPool {
    constructor() {
        this.connections = new Map();
        this.maxConnections = 5;
    }

    async getConnection(agentId, accessToken) {
        const key = `${agentId}-${accessToken}`;
        
        if (!this.connections.has(key)) {
            if (this.connections.size >= this.maxConnections) {
                // Close oldest connection
                const oldestKey = this.connections.keys().next().value;
                this.connections.get(oldestKey).close();
                this.connections.delete(oldestKey);
            }
            
            const connection = new PrismAgentVoiceChat(agentId, accessToken);
            this.connections.set(key, connection);
        }
        
        return this.connections.get(key);
    }
}
```

### Message Batching

```javascript
class MessageBatcher {
    constructor(socket, batchSize = 10, batchTimeout = 100) {
        this.socket = socket;
        this.batchSize = batchSize;
        this.batchTimeout = batchTimeout;
        this.messageQueue = [];
        this.timeoutId = null;
    }

    send(message) {
        this.messageQueue.push(message);
        
        if (this.messageQueue.length >= this.batchSize) {
            this.flush();
        } else if (!this.timeoutId) {
            this.timeoutId = setTimeout(() => this.flush(), this.batchTimeout);
        }
    }

    flush() {
        if (this.messageQueue.length > 0) {
            // Send batched messages
            this.messageQueue.forEach(message => {
                this.socket.send(JSON.stringify(message));
            });
            this.messageQueue = [];
        }
        
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }
    }
}
```

## Best Practices

1. **Always authenticate first** - Send the init message immediately after connection
2. **Handle authentication errors gracefully** - Implement retry logic and fallback UI
3. **Validate file IDs** before sending to ensure security
4. **Use token refresh** to maintain long-lived connections
5. **Implement connection pooling** for multiple agents
6. **Buffer audio chunks** for smooth playback
7. **Use secure WebSocket (WSS)** in production
8. **Implement proper error handling** for all message types
9. **Show processing indicators** to improve user experience
10. **Use real-time text mode** for instant responses when possible
11. **Optimize audio settings** for best quality and performance
12. **Never expose tokens** in client-side logs or storage

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Check token validity and expiration
   - Ensure proper token format (JWT)
   - Verify token has required permissions

2. **Connection Drops**
   - Implement reconnection logic
   - Check network connectivity
   - Verify server availability

3. **Audio Issues**
   - Check browser audio permissions
   - Verify audio format compatibility
   - Test with different audio settings

4. **Message Delivery Issues**
   - Ensure proper JSON formatting
   - Check message size limits
   - Verify WebSocket connection state

This documentation provides everything needed to integrate Prism Agent's authenticated AI chat functionality into your frontend application with full audio, text, and file context support.
