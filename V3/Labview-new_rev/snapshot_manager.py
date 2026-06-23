"""
Snapshot Manager - Handles snapshot creation, storage, and retrieval with batch support
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd
import io
import base64


class Snapshot:
    """Represents a single graph snapshot with view state and data"""

    def __init__(self, name: str, csv_source: str, view_settings: Dict[str, Any],
                 data: pd.DataFrame, statistics: Dict[str, Dict[str, float]]):
        self.id = str(uuid.uuid4())
        self.name = name
        self.created = datetime.now()
        self.csv_source = csv_source
        self.view_settings = view_settings
        self.data = data
        self.statistics = statistics
        self.thumbnail = None
        self.notes = ""
        self.batch_id = None  # Which batch this snapshot belongs to
        self.measurements = []  # List of measurement annotations

    def to_dict(self) -> Dict[str, Any]:
        """Serialize snapshot to dictionary for JSON storage"""
        # Convert DataFrame to JSON-serializable format
        data_dict = {}
        if self.data is not None and not self.data.empty:
            # Store timestamps as strings
            if 'Timestamp' in self.data.columns:
                data_dict['timestamps'] = self.data['Timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()

            # Store sensor values
            for col in self.data.columns:
                if col != 'Timestamp':
                    data_dict[col] = self.data[col].tolist()

        return {
            'id': self.id,
            'name': self.name,
            'created': self.created.isoformat(),
            'csv_source': self.csv_source,
            'view_settings': self.view_settings,
            'data': data_dict,
            'statistics': self.statistics,
            'thumbnail': self.thumbnail,
            'notes': self.notes,
            'batch_id': self.batch_id,
            'measurements': self.measurements
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Snapshot':
        """Deserialize snapshot from dictionary"""
        # Reconstruct DataFrame from stored data
        df_data = {}
        if 'data' in data and data['data']:
            stored_data = data['data']

            # Reconstruct timestamps
            if 'timestamps' in stored_data:
                df_data['Timestamp'] = pd.to_datetime(stored_data['timestamps'])

            # Reconstruct sensor values
            for key, values in stored_data.items():
                if key != 'timestamps':
                    df_data[key] = values

        df = pd.DataFrame(df_data) if df_data else pd.DataFrame()

        # Create snapshot object
        snapshot = Snapshot(
            name=data['name'],
            csv_source=data.get('csv_source', 'Unknown'),
            view_settings=data.get('view_settings', {}),
            data=df,
            statistics=data.get('statistics', {})
        )

        snapshot.id = data['id']
        snapshot.created = datetime.fromisoformat(data['created'])
        snapshot.thumbnail = data.get('thumbnail')
        snapshot.notes = data.get('notes', '')
        snapshot.batch_id = data.get('batch_id')
        snapshot.measurements = data.get('measurements', [])

        return snapshot


class Batch:
    """Represents a collection/batch of related snapshots"""

    def __init__(self, name: str):
        self.id = str(uuid.uuid4())
        self.name = name
        self.created = datetime.now()
        self.description = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize batch to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'created': self.created.isoformat(),
            'description': self.description
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Batch':
        """Deserialize batch from dictionary"""
        batch = Batch(name=data['name'])
        batch.id = data['id']
        batch.created = datetime.fromisoformat(data['created'])
        batch.description = data.get('description', '')
        return batch


class SnapshotManager:
    """Manages collection of snapshots and batches"""

    def __init__(self):
        self.snapshots: List[Snapshot] = []
        self.batches: List[Batch] = []
        self.current_batch_id: Optional[str] = None

    def create_batch(self, name: str) -> Batch:
        """Create a new batch"""
        batch = Batch(name=name)
        self.batches.append(batch)
        self.current_batch_id = batch.id
        print(f"[SNAPSHOT_MGR] Created batch '{name}' ({batch.id})")
        return batch

    def get_batch(self, batch_id: str) -> Optional[Batch]:
        """Get batch by ID"""
        for batch in self.batches:
            if batch.id == batch_id:
                return batch
        return None

    def get_all_batches(self) -> List[Batch]:
        """Get all batches"""
        return self.batches

    def rename_batch(self, batch_id: str, new_name: str) -> bool:
        """Rename a batch"""
        batch = self.get_batch(batch_id)
        if batch:
            batch.name = new_name
            return True
        return False

    def delete_batch(self, batch_id: str, delete_snapshots: bool = False) -> bool:
        """Delete a batch. Optionally delete all snapshots in it."""
        if delete_snapshots:
            # Delete all snapshots in this batch
            self.snapshots = [s for s in self.snapshots if s.batch_id != batch_id]

        # Remove batch
        for i, batch in enumerate(self.batches):
            if batch.id == batch_id:
                del self.batches[i]
                if self.current_batch_id == batch_id:
                    self.current_batch_id = self.batches[0].id if self.batches else None
                return True
        return False

    def get_snapshots_in_batch(self, batch_id: str) -> List[Snapshot]:
        """Get all snapshots in a specific batch"""
        return [s for s in self.snapshots if s.batch_id == batch_id]

    def get_unbatched_snapshots(self) -> List[Snapshot]:
        """Get snapshots not assigned to any batch"""
        return [s for s in self.snapshots if s.batch_id is None]

    def create_snapshot(self, name: str, csv_source: str, view_settings: Dict[str, Any],
                       data: pd.DataFrame, statistics: Dict[str, Dict[str, float]],
                       batch_id: Optional[str] = None) -> Snapshot:
        """Create a new snapshot"""
        # Decimate data if too large (keep max 500 points)
        decimated_data = self._decimate_data(data, max_points=500)

        snapshot = Snapshot(
            name=name,
            csv_source=csv_source,
            view_settings=view_settings,
            data=decimated_data,
            statistics=statistics
        )

        # Assign to batch (use current batch if not specified)
        if batch_id:
            snapshot.batch_id = batch_id
        elif self.current_batch_id:
            snapshot.batch_id = self.current_batch_id

        self.snapshots.append(snapshot)
        return snapshot

    def _decimate_data(self, df: pd.DataFrame, max_points: int = 500) -> pd.DataFrame:
        """Reduce data points for efficient storage"""
        if df is None or df.empty:
            return df

        if len(df) <= max_points:
            return df.copy()

        # Calculate stride to achieve approximately max_points
        stride = len(df) // max_points
        if stride < 1:
            stride = 1

        # Use iloc to sample every nth row
        decimated = df.iloc[::stride].copy()

        return decimated

    def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """Get snapshot by ID"""
        for snapshot in self.snapshots:
            if snapshot.id == snapshot_id:
                return snapshot
        return None

    def get_all_snapshots(self) -> List[Snapshot]:
        """Get all snapshots"""
        return self.snapshots

    def rename_snapshot(self, snapshot_id: str, new_name: str) -> bool:
        """Rename a snapshot"""
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot:
            snapshot.name = new_name
            return True
        return False

    def update_snapshot_notes(self, snapshot_id: str, notes: str) -> bool:
        """Update snapshot notes"""
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot:
            snapshot.notes = notes
            return True
        return False

    def move_snapshot_to_batch(self, snapshot_id: str, batch_id: Optional[str]) -> bool:
        """Move snapshot to a different batch"""
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot:
            snapshot.batch_id = batch_id
            return True
        return False

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete snapshot by ID"""
        for i, snapshot in enumerate(self.snapshots):
            if snapshot.id == snapshot_id:
                del self.snapshots[i]
                return True
        return False

    def delete_multiple_snapshots(self, snapshot_ids: List[str]) -> int:
        """Delete multiple snapshots. Returns count of deleted snapshots."""
        deleted = 0
        for snapshot_id in snapshot_ids:
            if self.delete_snapshot(snapshot_id):
                deleted += 1
        return deleted

    def clear_all(self):
        """Clear all snapshots and batches"""
        self.snapshots.clear()
        self.batches.clear()
        self.current_batch_id = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize all snapshots and batches to dictionary"""
        return {
            'snapshots': [s.to_dict() for s in self.snapshots],
            'batches': [b.to_dict() for b in self.batches],
            'current_batch_id': self.current_batch_id
        }

    def from_dict(self, data: Dict[str, Any]):
        """Deserialize snapshots and batches from dictionary"""
        self.snapshots.clear()
        self.batches.clear()

        # Load batches first
        if 'batches' in data:
            for batch_dict in data['batches']:
                batch = Batch.from_dict(batch_dict)
                self.batches.append(batch)

        # Load snapshots
        if 'snapshots' in data:
            for snap_dict in data['snapshots']:
                snapshot = Snapshot.from_dict(snap_dict)
                self.snapshots.append(snapshot)

        # Restore current batch
        self.current_batch_id = data.get('current_batch_id')
