from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QListWidget, QListWidgetItem, QLabel, QDialogButtonBox,
                             QScrollBar, QLineEdit)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class MappingDialog(QDialog):
    """Simple dialog to map sensors between config and CSV."""
    
    def __init__(self, orphaned_sensors, new_sensors, matched_sensors, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reconcile Sensor Changes")
        self.setMinimumSize(1000, 600)
        
        # Store all sensors
        self.config_sensors = list(orphaned_sensors) + list(matched_sensors)
        self.csv_sensors = list(new_sensors) + list(matched_sensors)
        
        # Pre-map matched sensors
        self.user_mappings = {}
        for sensor in matched_sensors:
            self.user_mappings[sensor] = sensor
        
        # UI state
        self.selected_config_sensor = None
        self.config_search_text = ""
        self.csv_search_text = ""
        
        self.setup_ui()
        self.refresh_lists()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Instructions
        info = QLabel(
            "<b>CSV Sensor Reconciliation</b><br>"
            "• <span style='color: #4CAF50;'><b>Green sensors</b></span> are already matched between config and CSV<br>"
            "• <span style='color: black;'><b>White sensors</b></span> need mapping: Click config sensor, then CSV sensor to map<br>"
            "• Click a green sensor to unmap it"
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "padding: 10px; background-color: #e3f2fd; "
            "border-radius: 4px; border: 1px solid #90caf9;"
        )
        layout.addWidget(info)
        
        # Search boxes
        search_layout = QHBoxLayout()
        
        # Config search
        config_search_label = QLabel("Config Search:")
        self.config_search_input = QLineEdit()
        self.config_search_input.setPlaceholderText("Filter unmapped config sensors...")
        self.config_search_input.textChanged.connect(self.on_config_search_changed)
        self.config_clear_btn = QPushButton("Clear")
        self.config_clear_btn.clicked.connect(self.clear_config_search)
        
        search_layout.addWidget(config_search_label)
        search_layout.addWidget(self.config_search_input)
        search_layout.addWidget(self.config_clear_btn)
        
        search_layout.addSpacing(20)
        
        # CSV search
        csv_search_label = QLabel("CSV Search:")
        self.csv_search_input = QLineEdit()
        self.csv_search_input.setPlaceholderText("Filter unmapped CSV sensors...")
        self.csv_search_input.textChanged.connect(self.on_csv_search_changed)
        self.csv_clear_btn = QPushButton("Clear")
        self.csv_clear_btn.clicked.connect(self.clear_csv_search)
        
        search_layout.addWidget(csv_search_label)
        search_layout.addWidget(self.csv_search_input)
        search_layout.addWidget(self.csv_clear_btn)
        
        layout.addLayout(search_layout)
        
        # Lists side by side with synchronized scrollbar
        lists_layout = QHBoxLayout()
        
        # Config list
        config_box = QVBoxLayout()
        config_box.addWidget(QLabel("<b>Config Sensors</b>"))
        self.config_list = QListWidget()
        self.config_list.itemClicked.connect(self.on_config_clicked)
        # Hide individual scrollbars - we'll use a shared one
        self.config_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.config_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        config_box.addWidget(self.config_list)
        lists_layout.addLayout(config_box)
        
        # CSV list
        csv_box = QVBoxLayout()
        csv_box.addWidget(QLabel("<b>CSV Sensors</b>"))
        self.csv_list = QListWidget()
        self.csv_list.itemClicked.connect(self.on_csv_clicked)
        # Hide individual scrollbars - we'll use a shared one
        self.csv_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.csv_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        csv_box.addWidget(self.csv_list)
        lists_layout.addLayout(csv_box)
        
        # Shared vertical scrollbar on the right
        self.sync_scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self.sync_scrollbar.valueChanged.connect(self.on_sync_scroll)
        lists_layout.addWidget(self.sync_scrollbar)
        
        layout.addLayout(lists_layout)
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        auto_match_btn = QPushButton("🔄 Auto-Match Sensors")
        auto_match_btn.setToolTip("Automatically match sensors based on name similarity")
        auto_match_btn.clicked.connect(self.auto_match_sensors)
        button_layout.addWidget(auto_match_btn)
        
        clear_all_btn = QPushButton("Clear All Mappings")
        clear_all_btn.clicked.connect(self.clear_all_mappings)
        button_layout.addWidget(clear_all_btn)
        
        button_layout.addStretch()
        
        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        button_layout.addWidget(buttons)
        
        layout.addLayout(button_layout)
    
    def refresh_lists(self):
        """Refresh both lists with current mappings and search filters."""
        self.config_list.clear()
        self.csv_list.clear()
        
        # Separate mapped and unmapped config sensors
        mapped_config = []
        unmapped_config = []
        
        for sensor in self.config_sensors:
            if sensor in self.user_mappings:
                mapped_config.append(sensor)
            else:
                unmapped_config.append(sensor)
        
        # Separate mapped and unmapped CSV sensors
        mapped_csv = []
        unmapped_csv = []
        
        for sensor in self.csv_sensors:
            if sensor in self.user_mappings.values():
                mapped_csv.append(sensor)
            else:
                unmapped_csv.append(sensor)
        
        # Apply search filter to UNMAPPED sensors only
        filtered_unmapped_config = unmapped_config
        if self.config_search_text:
            filtered_unmapped_config = [s for s in unmapped_config if self.config_search_text.lower() in s.lower()]
        
        filtered_unmapped_csv = unmapped_csv
        if self.csv_search_text:
            filtered_unmapped_csv = [s for s in unmapped_csv if self.csv_search_text.lower() in s.lower()]
        
        # Build ALIGNED display lists where mapped pairs appear on the same row
        config_display_list = []
        csv_display_list = []
        
        # Add filtered unmapped sensors with gap at TOP (not middle)
        max_unmapped = max(len(filtered_unmapped_config), len(filtered_unmapped_csv))
        if max_unmapped > 0:
            # Calculate how many placeholders needed at the top for each side
            config_gap = max_unmapped - len(filtered_unmapped_config)
            csv_gap = max_unmapped - len(filtered_unmapped_csv)
            
            # Add gap placeholders at the TOP for the side with fewer sensors
            for i in range(config_gap):
                config_display_list.append(None)
            for i in range(csv_gap):
                csv_display_list.append(None)
            
            # Then add the actual unmapped sensors (aligned at bottom of unmapped section)
            config_display_list.extend(filtered_unmapped_config)
            csv_display_list.extend(filtered_unmapped_csv)
        
        # Add mapped pairs aligned on the same row
        for config_sensor in mapped_config:
            csv_sensor = self.user_mappings[config_sensor]
            config_display_list.append(config_sensor)
            csv_display_list.append(csv_sensor)
        
        # Add config sensors to list
        for sensor in config_display_list:
            if sensor is None:
                # Empty placeholder row
                item = QListWidgetItem("")
                item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
                item.setBackground(QColor("#f0f0f0"))
            else:
                item = QListWidgetItem(sensor)
                item.setData(Qt.ItemDataRole.UserRole, sensor)
                
                # Color based on mapping status
                if sensor in self.user_mappings:
                    # Mapped = Green (always visible)
                    item.setBackground(QColor("#4CAF50"))
                    item.setForeground(QColor("white"))
                elif sensor == self.selected_config_sensor:
                    # Selected for mapping = Yellow highlight
                    item.setBackground(QColor("#FFF59D"))
                    item.setForeground(QColor("black"))
                else:
                    # Unmapped = White
                    item.setBackground(QColor("white"))
                    item.setForeground(QColor("black"))
            
            self.config_list.addItem(item)
        
        # Add CSV sensors to list
        for sensor in csv_display_list:
            if sensor is None:
                # Empty placeholder row
                item = QListWidgetItem("")
                item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
                item.setBackground(QColor("#f0f0f0"))
            else:
                item = QListWidgetItem(sensor)
                item.setData(Qt.ItemDataRole.UserRole, sensor)
                
                # Color based on mapping status
                if sensor in self.user_mappings.values():
                    # Mapped = Green (always visible)
                    item.setBackground(QColor("#4CAF50"))
                    item.setForeground(QColor("white"))
                else:
                    # Unmapped = White
                    item.setBackground(QColor("white"))
                    item.setForeground(QColor("black"))
            
            self.csv_list.addItem(item)
        
        # Update synchronized scrollbar range
        config_max = self.config_list.verticalScrollBar().maximum()
        csv_max = self.csv_list.verticalScrollBar().maximum()
        max_range = max(config_max, csv_max)
        self.sync_scrollbar.setMaximum(max_range)
        self.sync_scrollbar.setPageStep(self.config_list.verticalScrollBar().pageStep())
    
    def on_config_clicked(self, item):
        """Select a config sensor for mapping."""
        sensor = item.data(Qt.ItemDataRole.UserRole)
        
        # If already mapped, unmap it
        if sensor in self.user_mappings:
            del self.user_mappings[sensor]
            self.selected_config_sensor = None
            self.refresh_lists()
        else:
            # Select for mapping (yellow highlight)
            self.selected_config_sensor = sensor
            self.refresh_lists()  # Refresh to show selection
    
    def on_csv_clicked(self, item):
        """Map selected config sensor to this CSV sensor."""
        if not self.selected_config_sensor:
            return
        
        csv_sensor = item.data(Qt.ItemDataRole.UserRole)
        
        # Remove any existing mapping to this CSV sensor
        for config, csv in list(self.user_mappings.items()):
            if csv == csv_sensor:
                del self.user_mappings[config]
        
        # Create new mapping
        self.user_mappings[self.selected_config_sensor] = csv_sensor
        self.selected_config_sensor = None
        self.refresh_lists()
    
    def on_sync_scroll(self, value):
        """Synchronize both lists when the shared scrollbar moves."""
        self.config_list.verticalScrollBar().setValue(value)
        self.csv_list.verticalScrollBar().setValue(value)
    
    def on_config_search_changed(self, text):
        """Handle config search text change."""
        self.config_search_text = text
        self.refresh_lists()
    
    def on_csv_search_changed(self, text):
        """Handle CSV search text change."""
        self.csv_search_text = text
        self.refresh_lists()
    
    def clear_config_search(self):
        """Clear config search box."""
        self.config_search_input.clear()
    
    def clear_csv_search(self):
        """Clear CSV search box."""
        self.csv_search_input.clear()
    
    def auto_match_sensors(self):
        """Automatically match sensors based on name similarity with conservative validation."""
        # Get currently unmapped sensors
        unmapped_config = [s for s in self.config_sensors if s not in self.user_mappings]
        unmapped_csv = [s for s in self.csv_sensors if s not in self.user_mappings.values()]
        
        # Helper: Normalize abbreviations (CTR→Center, LE→Left, RE→Right)
        def normalize_abbreviations(name):
            """Normalize common abbreviations in sensor names."""
            import re
            # Case-insensitive replacement
            name = re.sub(r'\bCTR\b', 'Center', name, flags=re.IGNORECASE)
            name = re.sub(r'\bLE\b', 'Left', name, flags=re.IGNORECASE)
            name = re.sub(r'\bRE\b', 'Right', name, flags=re.IGNORECASE)
            return name
        
        # Helper: Extract position indicators
        def extract_position(name):
            """Extract position indicator (Center/CTR, Left/LE, Right/RE) from sensor name."""
            name_lower = name.lower()
            if 'center' in name_lower or 'ctr' in name_lower:
                return 'center'
            elif 'left' in name_lower or ' le ' in name_lower or name_lower.endswith(' le'):
                return 'left'
            elif 'right' in name_lower or ' re ' in name_lower or name_lower.endswith(' re'):
                return 'right'
            return None
        
        # Helper: Validate position compatibility
        def positions_compatible(pos1, pos2):
            """Check if two position indicators are compatible."""
            if pos1 is None and pos2 is None:
                return True  # Both have no position, compatible
            if pos1 is None or pos2 is None:
                return True  # One has no position, allow match (position might be implicit)
            return pos1 == pos2  # Must match exactly
        
        # Helper: Extract key terms from sensor name
        def extract_key_terms(name):
            """Extract important terms from sensor name, ignoring common words and numbers."""
            import re
            # Common words to ignore
            stop_words = {'in', 'of', 'the', 'a', 'an', 'and', 'or', 'to', 'from', 'at', 'on'}
            # Normalize and split into words
            normalized = normalize_abbreviations(name.lower())
            # Remove punctuation and split
            words = re.findall(r'\b\w+\b', normalized)
            # Filter out stop words and single characters
            key_terms = {w for w in words if w not in stop_words and len(w) > 1 and not w.isdigit()}
            return key_terms
        
        # Helper: Word set similarity using Levenshtein on word sets
        def word_set_similarity(terms1, terms2):
            """Calculate similarity between two sets of key terms."""
            if not terms1 and not terms2:
                return 1.0
            if not terms1 or not terms2:
                return 0.0
            
            # Check how many terms match
            common = terms1 & terms2
            all_terms = terms1 | terms2
            
            if not all_terms:
                return 0.0
            
            # Jaccard similarity (intersection over union)
            jaccard = len(common) / len(all_terms) if all_terms else 0.0
            
            # Also check if all key terms from one set exist in the other
            if terms1.issubset(terms2) or terms2.issubset(terms1):
                # Bonus for subset match
                return max(jaccard, 0.9)
            
            return jaccard
        
        # Levenshtein distance function for character-level similarity
        def levenshtein_distance(s1, s2):
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)
            if len(s2) == 0:
                return len(s1)
            previous_row = list(range(len(s2) + 1))
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            return previous_row[-1]
        
        # Calculate similarity scores and find best matches
        new_mappings = {}
        used_csv_sensors = set()
        
        for config_sensor in unmapped_config:
            # Extract key terms and position from config sensor
            config_terms = extract_key_terms(config_sensor)
            config_pos = extract_position(config_sensor)
            config_normalized = normalize_abbreviations(config_sensor.lower())
            
            best_match = None
            best_score = 0.85  # Require at least 85% similarity (conservative)
            candidates = []  # Track all candidates for ambiguity detection
            
            for csv_sensor in unmapped_csv:
                if csv_sensor in used_csv_sensors:
                    continue
                
                # Step 1: Check for exact match (case-insensitive)
                if config_sensor.lower() == csv_sensor.lower():
                    best_match = csv_sensor
                    best_score = 1.0
                    candidates = [(csv_sensor, 1.0)]  # Clear winner
                    break  # Exact match found, no need to check others
                
                # Step 2: Extract key terms and position from CSV sensor
                csv_terms = extract_key_terms(csv_sensor)
                csv_pos = extract_position(csv_sensor)
                csv_normalized = normalize_abbreviations(csv_sensor.lower())
                
                # Step 3: Validate position compatibility
                if not positions_compatible(config_pos, csv_pos):
                    continue  # Position mismatch, skip this candidate
                
                # Step 4: Calculate word set similarity
                word_sim = word_set_similarity(config_terms, csv_terms)
                
                # Step 5: Calculate character-level similarity on normalized names
                char_distance = levenshtein_distance(config_normalized, csv_normalized)
                max_len = max(len(config_normalized), len(csv_normalized))
                char_sim = 1 - (char_distance / max_len) if max_len > 0 else 0
                
                # Step 6: Combined similarity (weight word similarity more)
                similarity = (word_sim * 0.6) + (char_sim * 0.4)
                
                # Step 7: Validate all key terms are present
                # If config has key terms, they should mostly be in CSV (or vice versa)
                if config_terms and csv_terms:
                    term_overlap = len(config_terms & csv_terms) / len(config_terms | csv_terms) if (config_terms | csv_terms) else 0
                    if term_overlap < 0.5:  # Less than 50% term overlap
                        continue  # Key terms don't match well enough
                
                # Track candidate
                if similarity >= 0.85:
                    candidates.append((csv_sensor, similarity))
            
            # Step 8: Ambiguity detection - only match if one candidate is clearly best
            if candidates:
                # Sort by score (highest first)
                candidates.sort(key=lambda x: x[1], reverse=True)
                best_candidate = candidates[0]
                
                # Check for ambiguity: if second-best is within 0.05, reject all
                if len(candidates) > 1:
                    second_best_score = candidates[1][1]
                    if best_candidate[1] - second_best_score < 0.05:
                        # Ambiguous - multiple good matches, reject all
                        print(f"Auto-match rejected (ambiguous): {config_sensor} has {len(candidates)} similar candidates")
                        continue
                
                # Accept the best match
                best_match = best_candidate[0]
                best_score = best_candidate[1]
            
            if best_match:
                new_mappings[config_sensor] = best_match
                used_csv_sensors.add(best_match)
                print(f"Auto-matched: {config_sensor} -> {best_match} (similarity: {best_score:.2f})")
        
        # Apply new mappings
        self.user_mappings.update(new_mappings)
        self.refresh_lists()
        
        print(f"Auto-matched {len(new_mappings)} sensor pairs (conservative mode)")
    
    def clear_all_mappings(self):
        """Clear all user-created mappings."""
        self.user_mappings.clear()
        self.refresh_lists()
        print("All mappings cleared")
    
    def get_mappings(self):
        """Return the user-created mappings."""
        return self.user_mappings
