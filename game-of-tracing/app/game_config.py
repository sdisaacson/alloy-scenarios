"""
Game configuration for War of Kingdoms

This file defines the game map, locations, and initial state
"""

# Define locations
LOCATIONS = {
    "southern_capital": {
        "name": "Southern Capital",
        "type": "capital",
        "faction": "southern",
        "connections": ["village_1", "village_3"],
        "initial_resources": 100,
        "initial_army": 1,
        "port": 5001
    },
    "northern_capital": {
        "name": "Northern Capital",
        "type": "capital",
        "faction": "northern",
        "connections": ["village_2", "village_6"],
        "initial_resources": 100,
        "initial_army": 1,
        "port": 5002
    },
    "village_1": {
        "name": "Village 1",
        "type": "village",
        "faction": "neutral",
        "connections": ["southern_capital", "village_2", "village_4"],
        "initial_resources": 50,
        "initial_army": 2,
        "port": 5003
    },
    "village_2": {
        "name": "Village 2",
        "type": "village",
        "faction": "neutral",
        "connections": ["northern_capital", "village_1", "village_5"],
        "initial_resources": 50,
        "initial_army": 3,
        "port": 5004
    },
    "village_3": {
        "name": "Village 3",
        "type": "village",
        "faction": "neutral",
        "connections": ["southern_capital", "village_5", "village_6"],
        "initial_resources": 50,
        "initial_army": 2,
        "port": 5005
    },
    "village_4": {
        "name": "Village 4",
        "type": "village",
        "faction": "neutral",
        "connections": ["village_1", "village_5"],
        "initial_resources": 50,
        "initial_army": 1,
        "port": 5006
    },
    "village_5": {
        "name": "Village 5",
        "type": "village",
        "faction": "neutral",
        "connections": ["village_2", "village_3", "village_4", "village_6"],
        "initial_resources": 50,
        "initial_army": 4,
        "port": 5007
    },
    "village_6": {
        "name": "Village 6",
        "type": "village",
        "faction": "neutral",
        "connections": ["northern_capital", "village_3", "village_5"],
        "initial_resources": 50,
        "initial_army": 2,
        "port": 5008
    }
}

# Resource generation per turn
RESOURCE_GENERATION = {
    "capital": 20,
    "village": 10
}

# Costs
COSTS = {
    "create_army": 30
}

# Game state database
DATABASE_FILE = "game_state.db" 