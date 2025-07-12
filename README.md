# CrewAI Playground

A modern web interface for interacting with CrewAI crews through an intuitive, feature-rich chat UI.

<img width="1618" height="966" alt="Screenshot 2025-07-12 at 10 22 25" src="https://github.com/user-attachments/assets/9e41d5ae-7cd7-49db-acc8-06ebb8fb081b" />

<img width="1616" height="964" alt="Screenshot 2025-07-12 at 10 22 55" src="https://github.com/user-attachments/assets/0029bc08-f09d-404c-b8ef-07c556003b14" />

<img width="1614" height="964" alt="Screenshot 2025-07-12 at 10 23 20" src="https://github.com/user-attachments/assets/add0947c-46ec-43c8-9a1f-a5eff5d186af" />


*Screenshot: CrewAI Playground in action*

## Features

- 🌐 **Modern Web Interface**: Sleek, responsive chat UI for interacting with your CrewAI crews
- 🔍 **Auto-Discovery**: Automatically finds and loads your crew from the current directory
- 🎮 **Interactive**: Real-time chat with typing indicators and message formatting
- 📋 **Chat History**: Save and manage conversation threads with local storage
- 🗑️ **Thread Management**: Create new chats and delete old conversations
- 🔄 **State Persistence**: Conversations are saved and can be resumed
- 📱 **Responsive Design**: Optimized for various screen sizes
- 🚀 **Easy to Use**: Simple installation and setup process
- 🧵 **Multi-Thread Support**: Maintain multiple conversations with proper message tracking
- 🔔 **Cross-Thread Notifications**: Get notified when responses arrive in other threads
- 💬 **Persistent Typing Indicators**: Typing bubbles remain visible when switching threads
- 🔄 **Synchronization**: Messages are properly synchronized between client and server
- 🔧 **Tool Execution**: Support for executing CrewAI tools directly from the UI
- 📊 **Telemetry & Tracing**: Built-in OpenTelemetry integration for monitoring crew executions
- 🌊 **Flow API Support**: Create, manage, and visualize CrewAI flows through the UI
- 🔄 **Real-time Flow Visualization**: WebSocket-based real-time updates for flow executions
- 📝 **Structured Inputs**: Support for providing structured inputs to crews and flows

## Installation

### From PyPI (when published)

```bash
pip install crewai-playground
```

### From source

1. Clone this repository or download the source code
2. Navigate to the directory containing the `pyproject.toml` file
3. Install with pip:

```bash
pip install -e .
```

## Requirements

- Python 3.9+
- CrewAI 0.98.0+
- A properly configured CrewAI project with a crew instance

## Usage

1. Navigate to your CrewAI project directory
2. Run the chat UI:

```bash
crewai-playground
```

3. Open your browser and go to `http://localhost:5000`
4. Start chatting with your crew!

## How It Works

The CrewAI Playground:

1. Searches for crew.py or *_crew.py files in your current directory
2. Loads your crew instance
3. Uses the crew's chat_llm to initialize a chat interface
4. Provides a modern web-based UI for interacting with your crew
5. Manages chat history using local storage for persistent conversations
6. Discovers and makes available CrewAI tools for direct execution
7. Automatically discovers and loads CrewAI flows from your project
8. Provides real-time visualization of crew and flow executions
9. Collects telemetry data for monitoring and debugging

## Configuration

The chat UI uses the following configuration from your crew:

- `chat_llm`: The language model to use for chat interactions (required)
- Crew task descriptions: To understand your crew's purpose
- Agent descriptions: To understand the agents' roles

### Flow Configuration

CrewAI Playground automatically discovers flows in your project directory. You can specify a custom flows directory using the environment variable:

```bash
CREWAI_FLOWS_DIR=/path/to/flows crewai-playground
```

### Telemetry Configuration

Telemetry is enabled by default using OpenTelemetry. The application will:

- Log traces to the console for debugging
- Connect to an OpenTelemetry collector at `localhost:4318` if available
- Store execution traces in memory for viewing in the UI

### Tool Configuration

Tools are automatically discovered from your CrewAI installation. No additional configuration is required.

## Development

### Project Structure

```
src/
└── crewai_playground/
    ├── __init__.py        # Package initialization
    ├── server.py          # Web server implementation
    ├── crew_loader.py     # Logic to load user's crew
    ├── chat_handler.py    # Chat functionality
    ├── flow_api.py        # Flow API endpoints and WebSocket handling
    ├── flow_loader.py     # Logic to discover and load flows
    ├── telemetry.py       # OpenTelemetry integration
    ├── tool_loader.py     # Logic to discover and load tools
    ├── event_listener.py  # Event listeners for crew visualization
    └── ui/                # Modern React frontend
        └── build/         # Built frontend assets
    └── static/            # Legacy frontend assets
        ├── index.html     # Main UI page
        ├── styles.css     # Styling
        └── scripts.js     # Client-side functionality
pyproject.toml          # Package configuration
README.md               # Documentation
```

### UI Features

#### Chat History Management

The UI provides several ways to manage your conversations:

- **Create New Chat**: Click the "New Chat" button in the sidebar to start a fresh conversation
- **View Past Conversations**: All your conversations are saved and accessible from the sidebar
- **Delete Conversations**: Each conversation in the sidebar has a delete button (trash icon) to remove unwanted threads
- **Clear Current Chat**: The "Clear" button in the header removes all messages in the current conversation while keeping the thread

#### Thread Management

The application supports sophisticated thread management:

- **Multiple Concurrent Threads**: Maintain multiple conversations with different crews simultaneously
- **Thread Persistence**: All messages are correctly stored in their respective threads
- **Cross-Thread Notifications**: When a response arrives in a thread you're not currently viewing, you'll receive a notification
- **Persistent Typing Indicators**: Typing bubbles remain visible when switching between threads until a response is received
- **Thread Synchronization**: Messages are properly synchronized between client and server to ensure no messages are lost

### Advanced Features

#### Flow API

The CrewAI Playground includes comprehensive support for CrewAI Flows:

- **Flow Discovery**: Automatically finds and loads Flow classes from your project
- **Flow Execution**: Execute flows with structured inputs through the UI
- **Real-time Visualization**: Monitor flow execution with WebSocket-based updates
- **Flow State Management**: Track the state of flow executions and their steps
- **Flow Traces**: View detailed execution traces for debugging and analysis

To use the Flow API:

1. Create Flow classes in your project following the CrewAI Flow conventions
2. Start CrewAI Playground in your project directory
3. Access the Flows tab in the UI to see your available flows
4. Select a flow and provide the required inputs to execute it
5. Monitor the execution in real-time through the visualization interface

#### Telemetry & Tracing

The CrewAI Playground includes built-in telemetry capabilities:

- **OpenTelemetry Integration**: Collect and export traces using the OpenTelemetry standard
- **Execution Tracing**: Track crew, agent, and task executions with detailed spans
- **In-Memory Storage**: View traces directly in the UI without external dependencies
- **Collector Support**: Export traces to an OpenTelemetry collector if available
- **Visualization**: Explore execution traces with a visual interface

The telemetry features help you:

- Debug complex crew interactions
- Analyze agent performance and behavior
- Understand the flow of information between agents and tasks
- Optimize your crew designs based on execution patterns

#### Tool Execution

CrewAI Playground provides direct access to CrewAI tools:

- **Tool Discovery**: Automatically finds and loads tools from your CrewAI installation
- **Tool Execution**: Execute tools directly from the UI with structured inputs
- **Schema Validation**: Input validation based on tool schemas
- **Result Visualization**: View tool execution results in a formatted display

This feature allows you to:

- Test tools independently of crew executions
- Debug tool behavior with different inputs
- Understand tool capabilities and requirements
- Develop and test new tools more efficiently

### Development

#### Building the Package

To build the package:

```bash
pip install build
python -m build
```

The package will be available in the `dist/` directory.



## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
