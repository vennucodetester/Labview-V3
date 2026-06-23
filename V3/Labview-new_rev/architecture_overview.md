# HVAC Diagnostic Application - Architecture Overview

## 1. High-Level Overview
The application is a Python-based desktop tool for analyzing HVAC/Refrigeration cycle performance. It uses **PyQt6** for the Graphical User Interface and **Pandas** for data processing. The core functionality involves mapping sensor data (CSV/Excel) to a visual diagram of a refrigeration cycle and performing thermodynamic calculations (using **CoolProp**) to assess system health.

## 2. Directory Structure (`HVAC_Diagnostic/`)
- **`app.py`**: Main entry point. Initializes the `MainWindow` and application event loop.
- **`data_manager.py`**: Centralized state management. Handles data loading, caching, and signals.
- **`diagram_widget.py`**: The interactive visual editor for the system diagram.
- **`calculation_orchestrator.py`**: Bridges the diagram model (abstract) to the calculation engine (concrete data).
- **`calculation_engine.py`**: Pure physics engine. Calculates P-h points, superheat, subcooling, etc., using CoolProp.
- **`component_schemas.py`**: Definitions for UI components (Compressor, Condenser, etc.).
- **`*widget.py`**: Various UI tabs (Graph, Comparison, Calculations).

## 3. Key Components & Data Flow

### 3.1 Data Manager (`data_manager.py`)
- **Role**: Source of Truth.
- **Key Attributes**:
    - `csv_data`: Pandas DataFrame containing raw sensor logs.
    - `diagram_model`: JSON-serializable dictionary defining the system topology (Components + Pipes + Sensor Mappings).
    - `sensor_roles`: Maps logical system points (e.g., "Compressor Inlet") to physical CSV column names (e.g., "AI_1_T").
- **Key Methods**:
    - `load_csv()` / `load_session()`: Ingests data.
    - `reconcile_csv()`: Handles schema evolution when CSV columns change.
    - `get_sensor_value()`: API for other components to fetch current data.

### 3.2 Diagram Widget (`diagram_widget.py`)
- **Role**: Visual Configuration.
- **Functionality**:
    - Allows users to drag-and-drop HVAC components.
    - Connects components with pipes.
    - **Mapping**: Users click component ports to map them to CSV columns from `DataManager`.
- **Interaction**: Emits changes to `diagram_model`, which triggers re-calculations.

### 3.3 Calculation Pipeline
The calculation flow is a 2-step process:

1.  **Resolve Sensors (`calculation_orchestrator.py`)**:
    - Queries `diagram_model` to find which CSV columns correspond to required physics inputs (e.g., $P_{suction}$, $T_{evap\_out}$).
    - Handles complex logic like averaging multiple circuits (Left/Center/Right coils).

2.  **Physics Calculation (`calculation_engine.py`)**:
    - **Step 1: Rated Inputs**: Calculates Volumetric Efficiency ($\eta_{vol}$) based on user-provided rated specs (Capacity, Power, etc.).
    - **Step 2: Row-by-Row**: Iterates through the DataFrame. For each timestamp:
        - Converts units (PSIG $\to$ Pa, F $\to$ K).
        - Calls `CoolProp` to look up Enthalpy ($h$), Entropy ($s$), Density ($\rho$).
        - Computes 8-Point Cycle (Compressor In/Out, Condenser In/Out, TXV In/Out, Evap In/Out).
        - Derives Performance Metrics (COP, EER, Capacity, Mass Flow).

## 4. Dependencies
- **PyQt6**: UI Framework.
- **Pandas**: Data Manipulation.
- **CoolProp**: Thermodynamic Properties Database (Critical for physics).
- **OpenPyXL**: Excel file reading.

## 5. Potential Modification Areas
Based on the architecture, interactions for "modifying the code base" likely involve:
- **`calculation_engine.py`**: To change physics formulas or refrigerant definitions.
- **`calculation_orchestrator.py`**: To change how sensors are aggregated or mapped.
- **`diagram_widget.py`**: To add new component visual types or interaction modes.
