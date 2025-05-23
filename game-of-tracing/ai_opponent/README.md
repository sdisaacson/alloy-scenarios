# AI Opponent for War of Kingdoms

This Flask-based AI service provides an intelligent opponent for single-player games in the War of Kingdoms distributed tracing tutorial.

## Features

### Adaptive Strategy
The AI adapts its strategy based on the game phase:
- **Early Game (0-5 minutes)**: Focuses on resource collection and capturing neutral villages
- **Mid Game (5-15 minutes)**: Balances expansion with army building and defense
- **Late Game (15+ minutes)**: Shifts to aggressive tactics and all-out attacks

### Natural Behavior
- Takes 15-45 second pauses between actions to simulate human thinking time
- Uses weighted random decisions to avoid predictable patterns
- Reacts to player threats by reinforcing endangered locations
- Manages resources by transferring them from villages to capitals

### Decision Making
The AI analyzes the game state to make intelligent decisions:
1. **Threat Analysis**: Identifies enemy armies near its territories
2. **Expansion Targets**: Finds neutral villages and weak enemy locations
3. **Resource Management**: Collects resources and creates armies when needed
4. **Strategic Movement**: Reinforces threatened locations and attacks vulnerable targets

### OpenTelemetry Integration
All AI actions are fully instrumented with OpenTelemetry:
- Traces show decision-making process
- Spans include game phase, threats, and chosen actions
- Integrates with the game's distributed tracing pipeline

## API Endpoints

- `POST /activate` - Activate the AI for a specific faction
- `POST /deactivate` - Deactivate the AI
- `GET /status` - Get current AI status
- `GET /health` - Health check endpoint

## How It Works

1. When activated, the AI starts a background thread that runs the decision loop
2. Every 15-45 seconds, it:
   - Fetches the current game state from all locations
   - Analyzes threats and opportunities
   - Makes a weighted random decision based on the game phase
   - Executes the chosen action via location server APIs
3. The AI automatically stops when it detects game over

## Configuration

The AI difficulty is set to "normal" and provides a balanced challenge. Decision weights can be adjusted in the `DECISION_WEIGHTS` dictionary to make the AI more aggressive or defensive.

## Usage

The AI is integrated with the War Map UI:
1. Players can toggle "Enable AI Opponent" in the game interface
2. The AI automatically takes control of the faction not chosen by the player
3. For two-player games, keep the AI toggle off

## Observability

Monitor AI behavior through:
- **Traces**: View AI decision-making and action execution
- **Logs**: Track AI state changes and decisions
- **Service Map**: See AI interactions with location servers 