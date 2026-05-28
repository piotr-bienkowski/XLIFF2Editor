import sys
import json
import re
import time
from pathlib import Path
from lxml import etree
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QMessageBox,
                             QListWidget, QSplitter, QHeaderView, QAbstractItemView,
                             QProgressDialog, QStyledItemDelegate, QTextEdit, QPlainTextEdit,
                             QInputDialog, QDialog, QLabel, QLineEdit, QPushButton, QFormLayout,
                             QMenu, QColorDialog, QToolBar, QComboBox, QSizePolicy, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QRegularExpression, QModelIndex
from PyQt6.QtGui import (QAction, QKeySequence, QPalette, QColor, QTextDocument,
                         QAbstractTextDocumentLayout, QTextCharFormat, QTextCursor,
                         QBrush, QKeyEvent, QFont, QTextOption, QPainter, QPen, QPainterPath)
from PyQt6.QtWidgets import QStyle
from bs4 import BeautifulSoup, Tag, NavigableString
from fuzzywuzzy import fuzz
import anthropic
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from openai import OpenAI as OpenAIClient
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import deepl
    DEEPL_AVAILABLE = True
except ImportError:
    DEEPL_AVAILABLE = False

try:
    import enchant
    from enchant.checker import SpellChecker
    ENCHANT_AVAILABLE = True
except ImportError:
    ENCHANT_AVAILABLE = False
    print("Warning: pyenchant not available. Spell checking will be disabled.")

MODULE_DIR = Path(__file__).parent
XCONFIG_PATH = MODULE_DIR / "xconfig.json"
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

# --- Custom Editor Widget for Tag Protection ---

class TagProtectedTextEdit(QPlainTextEdit):
    """Custom text editor that makes tag regions non-editable"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tag_positions = []  # List of (start, end) tuples for tag positions
        self.setWordWrapMode(QTextOption.WrapMode.WordWrap)

        # Spell checking initialization
        self.spell_checker = None
        self.misspelled_words = []  # List of (start, end, word) tuples for misspelled words
        self.spell_check_enabled = ENCHANT_AVAILABLE
        self.underline_color = QColor(57, 255, 20)  # Default fluorescent green

        # Connect text changes to spell checking
        if self.spell_check_enabled:
            self.textChanged.connect(self.check_spelling)
        
    def setPlainText(self, text):
        """Override to detect and protect tags after setting text"""
        super().setPlainText(text)
        self.detect_and_protect_tags()
    
    def detect_and_protect_tags(self):
        """Find all tags in the text and mark them as read-only"""
        self.tag_positions = []
        text = self.toPlainText()
        
        # Find all tags: <1>, </1>, <1/>, etc.
        pattern = r'</?(\d+)/?>'
        
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        
        # Reset all formatting first
        cursor.select(QTextCursor.SelectionType.Document)
        normal_format = QTextCharFormat()
        cursor.setCharFormat(normal_format)
        
        # Now find and format tags
        for match in re.finditer(pattern, text):
            start = match.start()
            end = match.end()
            self.tag_positions.append((start, end))
            
            # Create format for tags
            tag_format = QTextCharFormat()
            tag_format.setForeground(QBrush(QColor(255, 0, 0)))  # Red color
            tag_format.setFontWeight(QFont.Weight.Bold)
            
            # Apply format
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(tag_format)
        
        cursor.endEditBlock()
    
    def is_position_in_tag(self, position):
        """Check if a cursor position is inside a tag"""
        for start, end in self.tag_positions:
            if start <= position < end:
                return True, start, end
        return False, -1, -1
    
    def is_position_between_paired_tags(self, position):
        """Check if cursor is between an opening and closing tag like <1>text</1> or <1></1>"""
        text = self.toPlainText()
        
        # Get text before and after cursor
        before = text[:position]
        after = text[position:]
        
        # Find the last opening tag before cursor: <N>
        # Use findall to get all matches, then take the last one
        opening_matches = list(re.finditer(r'<(\d+)>', before))
        if not opening_matches:
            return False
        
        # Get the last opening tag before cursor
        last_opening = opening_matches[-1]
        tag_num = last_opening.group(1)
        
        # Check if there's a corresponding closing tag after cursor: </N>
        closing_pattern = rf'^</{tag_num}>'
        if re.match(closing_pattern, after):
            # Cursor is directly between <N> and </N>, this is editable
            return True
        
        # Also check if there's text then closing tag
        closing_pattern = rf'</{tag_num}>'
        closing_match = re.search(closing_pattern, after)
        if closing_match:
            # Make sure there's no other opening tag of same number between cursor and closing
            between = after[:closing_match.start()]
            if not re.search(rf'<{tag_num}>', between):
                # We're between paired tags with possibly some text, this is editable
                return True
        
        return False
    
    def keyPressEvent(self, event: QKeyEvent):
        """Override to prevent editing inside tags"""
        cursor = self.textCursor()
        pos = cursor.position()
        
        # FIRST: Check if we're between paired tags (which is allowed for editing)
        # This must come before the in_tag check because we want to allow editing here
        if self.is_position_between_paired_tags(pos):
            # Allow normal editing between paired tags
            super().keyPressEvent(event)
            
            # After any edit, redetect tags
            if event.key() not in [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                                   Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                                   Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt]:
                self.detect_and_protect_tags()
            return
        
        # SECOND: Check if we're trying to edit inside a tag (not allowed)
        in_tag, tag_start, tag_end = self.is_position_in_tag(pos)
        
        # Block destructive operations inside tags
        if in_tag:
            # Allow navigation keys
            nav_keys = [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                       Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown]
            
            if event.key() in nav_keys:
                super().keyPressEvent(event)
                return
            
            # For backspace/delete at tag boundaries, move cursor past the tag
            if event.key() == Qt.Key.Key_Backspace:
                # Jump cursor to before the tag regardless of position inside it
                cursor.setPosition(tag_start)
                self.setTextCursor(cursor)
                return

            if event.key() == Qt.Key.Key_Delete:
                # Jump cursor to after the tag regardless of position inside it
                cursor.setPosition(tag_end)
                self.setTextCursor(cursor)
                return
            
            # Block any other key that would modify text inside tags
            if event.text() and not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # Jump cursor to end of tag instead
                cursor.setPosition(tag_end)
                self.setTextCursor(cursor)
                # Now insert the character after the tag
                super().keyPressEvent(event)
                return
        
        # Check if we have a selection that includes part of a tag
        if cursor.hasSelection():
            sel_start = cursor.selectionStart()
            sel_end = cursor.selectionEnd()
            
            # Check if selection overlaps with any tag
            for tag_start, tag_end in self.tag_positions:
                # If selection partially overlaps tag, prevent editing
                if (sel_start < tag_end and sel_end > tag_start and 
                    not (sel_start <= tag_start and sel_end >= tag_end)):
                    # Partial overlap - block modification
                    if event.key() in [Qt.Key.Key_Backspace, Qt.Key.Key_Delete] or event.text():
                        return
        
        # Block Backspace/Delete that would eat into a tag from outside
        if not cursor.hasSelection():
            if event.key() == Qt.Key.Key_Backspace and pos > 0:
                in_left, _, _ = self.is_position_in_tag(pos - 1)
                if in_left:
                    return
            if event.key() == Qt.Key.Key_Delete:
                in_right, _, _ = self.is_position_in_tag(pos)
                if in_right:
                    return

        # Normal processing
        super().keyPressEvent(event)

        # After any edit, redetect tags
        if event.key() not in [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                               Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                               Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt]:
            self.detect_and_protect_tags()
    
    def mousePressEvent(self, event):
        """Override to handle clicking on tags"""
        super().mousePressEvent(event)

        cursor = self.textCursor()
        pos = cursor.position()

        in_tag, tag_start, tag_end = self.is_position_in_tag(pos)

        if in_tag:
            # Select the entire tag when clicking on it
            cursor.setPosition(tag_start)
            cursor.setPosition(tag_end, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)

    # --- Spell Checking Methods ---

    def set_underline_color(self, color):
        """Set the color for spell checking underlines"""
        self.underline_color = color
        self.viewport().update()  # Trigger repaint

    def set_spell_checker_language(self, language_code):
        """Set the spell checker language based on language code (e.g., 'pl-PL', 'en-US')"""
        if not self.spell_check_enabled:
            return

        try:
            # Extract base language code (pl from pl-PL, en from en-US)
            if language_code and '-' in language_code:
                lang = language_code.split('-')[0].lower()
            else:
                lang = language_code.lower() if language_code else 'en'

            # Map common language codes
            lang_map = {
                'pl': 'pl_PL',
                'en': 'en_US',
                'de': 'de_DE',
                'fr': 'fr_FR',
                'es': 'es_ES',
                'it': 'it_IT',
                'pt': 'pt_BR',
                'ru': 'ru_RU',
            }

            enchant_lang = lang_map.get(lang, f'{lang}_US')

            # Check if dictionary is available
            if enchant.dict_exists(enchant_lang):
                self.spell_checker = enchant.Dict(enchant_lang)
                self.check_spelling()
            else:
                # Try simpler language code
                if enchant.dict_exists(lang):
                    self.spell_checker = enchant.Dict(lang)
                    self.check_spelling()
                else:
                    print(f"Warning: Dictionary for '{enchant_lang}' not available. Available: {enchant.list_languages()}")
                    self.spell_checker = None
        except Exception as e:
            print(f"Error setting spell checker language: {e}")
            self.spell_checker = None

    def extract_words(self, text):
        """Extract words from text, excluding tags and returning their positions"""
        words = []
        # Pattern to match words (Unicode letters, excluding tags)
        word_pattern = re.compile(r'\b[\w]+\b', re.UNICODE)

        for match in word_pattern.finditer(text):
            start = match.start()
            end = match.end()
            word = match.group()

            # Skip if word is inside a tag
            in_tag = False
            for tag_start, tag_end in self.tag_positions:
                if start >= tag_start and end <= tag_end:
                    in_tag = True
                    break

            if not in_tag and len(word) > 1:  # Skip single characters
                words.append((start, end, word))

        return words

    def check_spelling(self):
        """Check spelling of all words in the text"""
        if not self.spell_check_enabled or not self.spell_checker:
            self.misspelled_words = []
            self.viewport().update()
            return

        text = self.toPlainText()
        words = self.extract_words(text)

        self.misspelled_words = []
        for start, end, word in words:
            # Skip words that are all digits
            if word.isdigit():
                continue

            # Check spelling
            if not self.spell_checker.check(word):
                self.misspelled_words.append((start, end, word))

        # Trigger repaint to show underlines
        self.viewport().update()

    def paintEvent(self, event):
        """Override to draw red wavy underlines under misspelled words"""
        super().paintEvent(event)

        if not self.spell_check_enabled or not self.misspelled_words:
            return

        # Create painter for drawing underlines
        painter = QPainter(self.viewport())
        # Use configured color or default fluorescent green
        color = getattr(self, 'underline_color', QColor(57, 255, 20))
        pen = QPen(color)
        pen.setWidth(2)  # Thicker lines for better visibility
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)

        # Get the first visible block
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        # Iterate through visible blocks
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                block_text = block.text()
                block_start = block.position()

                # Draw underlines for misspelled words in this block
                for word_start, word_end, word in self.misspelled_words:
                    if block_start <= word_start < block_start + len(block_text):
                        # Calculate word position relative to block
                        relative_start = word_start - block_start
                        relative_end = word_end - block_start

                        # Get cursor positions for start and end
                        cursor_start = QTextCursor(block)
                        cursor_start.setPosition(block_start + relative_start)
                        cursor_end = QTextCursor(block)
                        cursor_end.setPosition(block_start + relative_end)

                        # Get rectangles for positions
                        rect_start = self.cursorRect(cursor_start)
                        rect_end = self.cursorRect(cursor_end)

                        # Draw wavy line
                        y = rect_start.bottom() - 1
                        x_start = rect_start.left()
                        x_end = rect_end.left()

                        # Draw zigzag pattern
                        path = QPainterPath()
                        path.moveTo(x_start, y)

                        x = x_start
                        wave_up = True
                        wave_width = 2

                        while x < x_end:
                            x += wave_width
                            if x > x_end:
                                x = x_end
                            y_offset = -2 if wave_up else 0
                            path.lineTo(x, y + y_offset)
                            wave_up = not wave_up

                        painter.drawPath(path)

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

        painter.end()

    def contextMenuEvent(self, event):
        """Override to add spelling suggestions to context menu"""
        # Create standard context menu
        menu = self.createStandardContextMenu()

        if self.spell_check_enabled and self.spell_checker:
            # Get cursor position at click
            cursor = self.cursorForPosition(event.pos())
            click_pos = cursor.position()

            # Check if we clicked on a misspelled word
            clicked_word = None
            for start, end, word in self.misspelled_words:
                if start <= click_pos <= end:
                    clicked_word = (start, end, word)
                    break

            if clicked_word:
                start, end, word = clicked_word

                # Get suggestions
                suggestions = self.spell_checker.suggest(word)

                # Add suggestions to menu at the top
                if suggestions:
                    menu.insertSeparator(menu.actions()[0] if menu.actions() else None)

                    # Add up to 5 suggestions
                    for suggestion in suggestions[:5]:
                        action = QAction(suggestion, self)
                        action.triggered.connect(
                            lambda checked, s=suggestion, st=start, en=end: self.replace_word(st, en, s)
                        )
                        menu.insertAction(menu.actions()[0] if menu.actions() else None, action)

                    # Add "Add to dictionary" option
                    menu.insertSeparator(menu.actions()[0] if menu.actions() else None)
                    add_action = QAction(f"Add '{word}' to dictionary", self)
                    add_action.triggered.connect(lambda checked, w=word: self.add_to_dictionary(w))
                    menu.insertAction(menu.actions()[0] if menu.actions() else None, add_action)
                else:
                    # No suggestions available
                    no_sugg_action = QAction("(No suggestions)", self)
                    no_sugg_action.setEnabled(False)
                    menu.insertAction(menu.actions()[0] if menu.actions() else None, no_sugg_action)
                    menu.insertSeparator(menu.actions()[1] if len(menu.actions()) > 1 else None)

        menu.exec(event.globalPos())

    def replace_word(self, start, end, replacement):
        """Replace a misspelled word with the selected suggestion"""
        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(replacement)
        self.setTextCursor(cursor)

        # Recheck spelling after replacement
        self.detect_and_protect_tags()
        self.check_spelling()

    def add_to_dictionary(self, word):
        """Add a word to the personal dictionary"""
        if self.spell_checker:
            try:
                self.spell_checker.add(word)
                self.check_spelling()  # Recheck to remove underline
            except Exception as e:
                print(f"Error adding word to dictionary: {e}")


# --- Tag Rendering Delegate ---

class RichTextDelegate(QStyledItemDelegate):
    """Renders the cell text with HTML support to show tags in red."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.editor_window = parent  # Store reference to main window
    
    def createEditor(self, parent, option, index):
        """Create custom editor with tag protection"""
        # Only use custom editor for target column (column 3)
        if index.column() == 3:  # Column 3 is now Target
            editor = TagProtectedTextEdit(parent)
            # Add orange border to the editor
            editor.setStyleSheet("QPlainTextEdit { border: 2px solid orange; }")

            # Disable scrollbars - we want the row to grow instead
            editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

            # Connect to text changes to update row height dynamically
            editor.textChanged.connect(lambda: self.adjust_editor_height(editor, index))

            # Set spell checker language from main window
            if self.editor_window and hasattr(self.editor_window, 'trg_lang'):
                if self.editor_window.trg_lang:
                    editor.set_spell_checker_language(self.editor_window.trg_lang)

            # Set underline color from main window
            if self.editor_window and hasattr(self.editor_window, 'current_underline_color'):
                editor.set_underline_color(self.editor_window.current_underline_color)

            return editor
        return super().createEditor(parent, option, index)
    
    def adjust_editor_height(self, editor, index):
        """Adjust row height based on editor content"""
        if not isinstance(editor, TagProtectedTextEdit):
            return
        
        # Calculate required height
        doc = editor.document()
        doc.setTextWidth(editor.width() - 10)  # Account for margins
        doc_height = doc.size().height()
        
        # Add padding for border and spacing
        required_height = int(doc_height) + 14  # Extra for orange border (2px * 2) + padding
        
        # Set minimum height
        if required_height < 30:
            required_height = 30
        
        # Get current row height
        table = self.editor_window.table
        current_height = table.rowHeight(index.row())
        
        # Only update if height needs to change
        if abs(current_height - required_height) > 5:
            table.setRowHeight(index.row(), required_height)
    
    def setEditorData(self, editor, index):
        """Set the editor's content from the model"""
        if isinstance(editor, TagProtectedTextEdit):
            text = index.data(Qt.ItemDataRole.DisplayRole)
            if text:
                editor.setPlainText(text)
        else:
            super().setEditorData(editor, index)
    
    def setModelData(self, editor, model, index):
        """Save the editor's content back to the model"""
        if isinstance(editor, TagProtectedTextEdit):
            model.setData(index, editor.toPlainText(), Qt.ItemDataRole.EditRole)
            # Explicitly set the modified flag
            if self.editor_window and hasattr(self.editor_window, 'is_modified'):
                self.editor_window.is_modified = True
        else:
            super().setModelData(editor, model, index)
    
    def updateEditorGeometry(self, editor, option, index):
        """Update the editor's geometry to fill the entire cell"""
        if isinstance(editor, TagProtectedTextEdit):
            # First, calculate and set the proper row height based on content
            doc = editor.document()
            doc.setTextWidth(option.rect.width() - 10)
            doc_height = doc.size().height()
            required_height = int(doc_height) + 14  # Account for border and padding
            
            if required_height < 30:
                required_height = 30
            
            # Update row height if needed
            table = self.editor_window.table
            if table.rowHeight(index.row()) < required_height:
                table.setRowHeight(index.row(), required_height)
            
            # Now set editor geometry to fill the entire cell
            # Use the actual row height, not the calculated one
            actual_row_height = table.rowHeight(index.row())
            editor_rect = option.rect
            editor_rect.setHeight(actual_row_height)
            editor.setGeometry(editor_rect)
        else:
            super().updateEditorGeometry(editor, option, index)
    
    def paint(self, painter, option, index):
        options = option
        self.initStyleOption(options, index)
        
        # Color tags red using regex
        text = options.text
        # Escape HTML entities in text first to avoid breaking rendering
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # Convert our placeholders back to red HTML spans
        # Matches <1>, </1>, and <1/>
        text = re.sub(r'(&lt;/?\d+/?&gt;)', r'<span style="color:red; font-weight:bold;">\1</span>', text)
        
        doc = QTextDocument()
        doc.setHtml(text)
        doc.setTextWidth(options.rect.width())  # Enable text wrapping
        
        painter.save()
        # Handle selection background
        if options.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(options.rect, options.palette.highlight())
            
        painter.translate(options.rect.x(), options.rect.y())
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        # Calculate proper height for wrapped text
        text = index.data()
        if text:
            # Escape HTML entities
            text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            text = re.sub(r'(&lt;/?\d+/?&gt;)', r'<span style="color:red; font-weight:bold;">\1</span>', text)
            
            doc = QTextDocument()
            doc.setHtml(text)
            doc.setTextWidth(option.rect.width())
            return doc.size().toSize()
        return super().sizeHint(option, index)

# --- Loading Threads ---

class TMXLoadThread(QThread):
    """Thread for loading TMX files with progress indication"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath
    
    def run(self):
        try:
            tmx_dict = {}
            for _event, elem in etree.iterparse(self.filepath, tag='tu'):
                tuvs = elem.findall('.//{*}tuv')
                if len(tuvs) >= 2:
                    src_seg = tuvs[0].find('{*}seg')
                    tgt_seg = tuvs[1].find('{*}seg')
                    if src_seg is not None and tgt_seg is not None:
                        src = (src_seg.text or '').strip()
                        tgt = (tgt_seg.text or '').strip()
                        if src:
                            tmx_dict[src] = tgt
                elem.clear()  # discard parsed node immediately to keep memory flat
            self.finished.emit(tmx_dict)
        except Exception as e:
            self.error.emit(str(e))


class XLIFFLoadThread(QThread):
    """Thread for loading XLIFF files with progress indication"""
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(object, list, str)  # soup, segments, filepath
    error = pyqtSignal(str)
    
    def __init__(self, filepath, parse_func):
        super().__init__()
        self.filepath = filepath
        self.parse_func = parse_func
    
    def run(self):
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                xliff_soup = BeautifulSoup(f.read(), 'xml')
            
            segments = []
            units = xliff_soup.find_all('unit')
            total = len(units)
            
            for idx, unit in enumerate(units):
                segment = unit.find('segment')
                if segment:
                    # Find which file this unit belongs to
                    file_element = unit.find_parent('file')
                    file_id = file_element.get('id', 'unknown') if file_element else 'unknown'
                    
                    src_node = segment.find('source')
                    tgt_node = segment.find('target')
                    
                    src_text, src_tag_map = self.parse_func(src_node)
                    tgt_text = ""
                    tgt_tag_map = {}
                    if tgt_node:
                        tgt_text, tgt_tag_map = self.parse_func(tgt_node)
                    
                    # Combine tag maps - use source as base, but update with target
                    # This ensures all tags from both source and target are available
                    combined_tag_map = src_tag_map.copy()
                    combined_tag_map.update(tgt_tag_map)
                    
                    # Check if segment is locked (translate="no")
                    is_locked = segment.get('translate', 'yes').lower() == 'no'
                    
                    segments.append({
                        'source': src_text,
                        'target': tgt_text,
                        'state': segment.get('state', 'initial'),
                        'segment_node': segment,
                        'tag_map': combined_tag_map,
                        'file_id': file_id,  # Track which file this segment belongs to
                        'locked': is_locked  # Track if segment is locked
                    })
                
                if idx % 100 == 0:  # Update progress every 100 segments
                    self.progress.emit(idx + 1, total)
            
            self.progress.emit(total, total)
            self.finished.emit(xliff_soup, segments, self.filepath)
        except Exception as e:
            self.error.emit(str(e))


# --- Core Thread Update ---

class AITranslationThread(QThread):
    progress = pyqtSignal(int, int)
    segment_translated = pyqtSignal(int, str, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    PROVIDERS = ['Claude', 'Gemini', 'OpenAI', 'DeepL']

    def __init__(self, provider, api_key, segments_to_translate, glossary, src_lang='', trg_lang='', context=''):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.segments_to_translate = segments_to_translate
        self.glossary = glossary
        self.src_lang = src_lang
        self.trg_lang = trg_lang
        self.context = context.strip()
        self.is_cancelled = False
        self._last_call_time = 0.0

    def _rate_limit(self):
        """Ensure at least 1 second between consecutive API calls."""
        elapsed = time.monotonic() - self._last_call_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_call_time = time.monotonic()

    def _build_prompt(self, source_text):
        lang_hint = f" to {self.trg_lang}" if self.trg_lang else ""
        glossary_text = ""
        if self.glossary:
            src_lower = source_text.lower()
            relevant = {k: v for k, v in self.glossary.items() if k.lower() in src_lower}
            if relevant:
                glossary_text = "\n\nGlossary (use these translations for the listed terms):\n" + \
                    "\n".join(f"- {k}: {v}" for k, v in relevant.items())
        context_text = f"\n\nContext: {self.context}" if self.context else ""
        return (
            f"Translate the following text{lang_hint}. "
            f"Output only the translation, no explanations or additional text.\n"
            f"If the text contains tags like <1>, </1>, or <2/>, keep them exactly as-is "
            f"and place them correctly in the translation."
            f"{glossary_text}"
            f"{context_text}\n\n"
            f"Text:\n{source_text}"
        )

    def _translate_anthropic(self):
        client = anthropic.Anthropic(api_key=self.api_key)
        total = len(self.segments_to_translate)
        for idx, (row, source_text) in enumerate(self.segments_to_translate):
            if self.is_cancelled:
                break
            self._rate_limit()
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": self._build_prompt(source_text)}]
            )
            self.segment_translated.emit(row, msg.content[0].text.strip(), "initial")
            self.progress.emit(idx + 1, total)

    def _translate_gemini(self):
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        total = len(self.segments_to_translate)
        for idx, (row, source_text) in enumerate(self.segments_to_translate):
            if self.is_cancelled:
                break
            self._rate_limit()
            response = model.generate_content(self._build_prompt(source_text))
            self.segment_translated.emit(row, response.text.strip(), "initial")
            self.progress.emit(idx + 1, total)

    def _translate_openai(self):
        client = OpenAIClient(api_key=self.api_key)
        total = len(self.segments_to_translate)
        for idx, (row, source_text) in enumerate(self.segments_to_translate):
            if self.is_cancelled:
                break
            self._rate_limit()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=2000,
                messages=[{"role": "user", "content": self._build_prompt(source_text)}]
            )
            self.segment_translated.emit(row, response.choices[0].message.content.strip(), "initial")
            self.progress.emit(idx + 1, total)

    def _to_deepl_xml(self, text):
        """Replace numeric tags <N> with valid XML names <tN> for DeepL."""
        text = re.sub(r'<(\d+)/>', r'<t\1/>', text)
        text = re.sub(r'</(\d+)>', r'</t\1>', text)
        text = re.sub(r'<(\d+)>', r'<t\1>', text)
        return text

    def _from_deepl_xml(self, text):
        """Restore numeric tags <N> after DeepL translation."""
        text = re.sub(r'<t(\d+)/>', r'<\1/>', text)
        text = re.sub(r'</t(\d+)>', r'</\1>', text)
        text = re.sub(r'<t(\d+)>', r'<\1>', text)
        return text

    def _deepl_target_lang(self, lang):
        """Convert XLIFF locale to a DeepL target language code.

        Most languages use only the 2-letter code (PL, DE, FR…).
        English and Portuguese require a regional variant (EN-US, PT-BR…).
        """
        if not lang:
            return None
        parts = lang.upper().replace('_', '-').split('-')
        if parts[0] in ('EN', 'PT') and len(parts) > 1:
            return f"{parts[0]}-{parts[1]}"
        if parts[0] == 'EN':
            return 'EN-US'  # default when no region provided
        if parts[0] == 'PT':
            return 'PT-PT'  # default when no region provided
        return parts[0]

    def _translate_deepl(self):
        translator = deepl.Translator(self.api_key)
        src = self.src_lang.split('-')[0].upper() if self.src_lang else None
        trg = self._deepl_target_lang(self.trg_lang)
        inline_tags = [f"t{i}" for i in range(1, 21)]
        total = len(self.segments_to_translate)
        for idx, (row, source_text) in enumerate(self.segments_to_translate):
            if self.is_cancelled:
                break
            self._rate_limit()
            xml_text = self._to_deepl_xml(source_text)
            result = translator.translate_text(
                xml_text,
                source_lang=src,
                target_lang=trg,
                tag_handling='xml',
                non_splitting_tags=inline_tags,
            )
            translation = self._from_deepl_xml(result.text.strip())
            self.segment_translated.emit(row, translation, "initial")
            self.progress.emit(idx + 1, total)

    def run(self):
        try:
            if self.provider == 'Claude':
                self._translate_anthropic()
            elif self.provider == 'Gemini':
                self._translate_gemini()
            elif self.provider == 'OpenAI':
                self._translate_openai()
            elif self.provider == 'DeepL':
                self._translate_deepl()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

# --- Main Editor ---

def _filter_matches(src_text: str, trg_text: str, src_pat, trg_pat, use_and: bool) -> bool:
    """Return True if a segment row should be visible given the active filter.

    src_pat / trg_pat: compiled re.Pattern for regex mode, plain str for
    case-insensitive contains, or None for no filter on that column.
    use_and: True = both non-None patterns must match; False = either suffices.
    """
    def hit(text: str, pat) -> bool:
        if isinstance(pat, str):
            return pat.lower() in text.lower()
        return bool(pat.search(text))

    if src_pat is None and trg_pat is None:
        return True
    if src_pat is not None and trg_pat is None:
        return hit(src_text, src_pat)
    if trg_pat is not None and src_pat is None:
        return hit(trg_text, trg_pat)
    sm, tm = hit(src_text, src_pat), hit(trg_text, trg_pat)
    return (sm and tm) if use_and else (sm or tm)

class XLIFFEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.xliff_file = None
        self.xliff_soup = None
        self.segments = [] # List of dicts with 'tag_map'
        self.tmx_data = {}
        self.current_row = -1
        self._is_modified = False  # Internal storage - must be set BEFORE the property is used
        self.ai_thread = None
        self.tmx_thread = None
        self.xliff_thread = None
        self.tmx_progress = None
        self.xliff_progress = None
        self.ai_progress = None
        self.src_lang = None  # Source language from XLIFF
        self.trg_lang = None  # Target language from XLIFF
        self.recent_files = []  # List of recently opened files
        self.max_recent_files = 10  # Maximum number of recent files to track
        self.font_size = 10  # Default font size
        self.underline_color = QColor(57, 255, 20)  # Default fluorescent green
        self.current_theme = "dark"  # overwritten after init_ui by detect_system_theme()

        self.load_xconfig()
        self.ai_provider = self.xconfig['settings'].get('ai_provider', 'Claude')
        self.glossary = {}
        self.load_glossary()
        detected_theme = self.detect_system_theme()
        self.init_ui()
        for ctx in self.xconfig.get('contexts', []):
            self.context_combo.addItem(ctx)
        self.current_theme = detected_theme
        self.apply_theme(self.current_theme)
        self.apply_font_size()
    
    @property
    def is_modified(self):
        """Get the modified status"""
        return self._is_modified
    
    @is_modified.setter
    def is_modified(self, value):
        """Set the modified status"""
        self._is_modified = value
    
    def keyPressEvent(self, event):
        """Handle custom keyboard shortcuts, specifically Left Alt + S"""
        # Check for Left Alt + S (copy source to target)
        if (event.key() == Qt.Key.Key_S and 
            event.modifiers() == Qt.KeyboardModifier.AltModifier):
            # On most systems, we can't distinguish left from right Alt in Qt
            # But Alt+S will work as the shortcut
            self.copy_source_to_target()
            event.accept()
            return
        
        # Pass to parent for normal handling
        super().keyPressEvent(event)
        
    def init_ui(self):
        self.setWindowTitle("Xliff 2 Editor")
        self.setGeometry(100, 100, 1300, 800)
        
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        
        actions = [
            ("Open XLIFF", "Ctrl+O", self.open_xliff),
        ]
        for name, shortcut, callback in actions:
            act = QAction(name, self)
            act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(callback)
            file_menu.addAction(act)
        
        # Add "Open Recent" submenu
        self.recent_menu = file_menu.addMenu("Open Recent")
        self.update_recent_files_menu()
        
        file_menu.addSeparator()

        # SDLXLIFF submenu
        sdlxliff_menu = file_menu.addMenu("SDLXLIFF")
        sdlxliff_actions = [
            ("Import from SDLXLIFF...", None, self.import_from_sdlxliff),
            ("Export to SDLXLIFF...", None, self.export_to_sdlxliff),
        ]
        for name, shortcut, callback in sdlxliff_actions:
            act = QAction(name, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(callback)
            sdlxliff_menu.addAction(act)

        # memoQ submenu
        mqxliff_menu = file_menu.addMenu("memoQ")
        mqxliff_actions = [
            ("Import from memoQ (MQXLIFF)...", None, self.import_from_mqxliff),
            ("Export to memoQ (MQXLIFF)...", None, self.export_to_mqxliff),
        ]
        for name, shortcut, callback in mqxliff_actions:
            act = QAction(name, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(callback)
            mqxliff_menu.addAction(act)

        # Excel submenu
        excel_menu = file_menu.addMenu("Excel")
        excel_actions = [
            ("Import from Excel...", None, self.import_from_excel),
            ("Export to Excel...",   None, self.export_to_excel),
        ]
        for name, shortcut, callback in excel_actions:
            act = QAction(name, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(callback)
            excel_menu.addAction(act)

        file_menu.addSeparator()
        
        # Continue with other file menu items
        actions = [
            ("Save XLIFF", "Ctrl+S", self.save_xliff),
            ("Save As...", "Ctrl+Shift+S", self.save_xliff_as),
            ("Close XLIFF", "Ctrl+W", self.close_xliff),
            (None, None, None),
            ("Set Target Language", "Ctrl+L", self.set_target_language),
            (None, None, None),
            ("Load TMX", "Ctrl+T", self.load_tmx),
            (None, None, None),
            ("Exit", "Ctrl+Q", self.close)
        ]
        for name, shortcut, callback in actions:
            if name is None:
                file_menu.addSeparator()
                continue
            act = QAction(name, self)
            act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(callback)
            file_menu.addAction(act)

        tasks_menu = menubar.addMenu("Tasks")
        task_actions = [
            ("Insert Next Tag", "Ctrl+N", self.insert_next_tag),
            ("Clear Current Target", "Ctrl+D", self.clear_current_target),
            ("Clear All Targets", "Ctrl+Shift+D", self.clear_all_targets),
            ("Set Status to Translated", "Ctrl+E", self.set_current_translated),
            (None, None, None),
            ("Copy Source to Target", "Alt+S", self.copy_source_to_target),
            ("Copy All Sources to Targets", "Ctrl+Shift+C", self.copy_all_sources_to_targets),
            (None, None, None),
            ("Edit Languages", "Ctrl+Shift+L", self.edit_languages),
            (None, None, None),
            ("AI Translate Current", "Ctrl+Shift+A", self.ai_translate_current),
            ("AI Translate All Initial", "Ctrl+Shift+T", self.ai_translate_all_initial),
        ]
        for name, shortcut, callback in task_actions:
            if name is None:
                tasks_menu.addSeparator()
                continue
            act = QAction(name, self)
            act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(callback)
            tasks_menu.addAction(act)

        # Options menu
        options_menu = menubar.addMenu("Options")
        font_size_action = QAction("Change Font Size...", self)
        font_size_action.triggered.connect(self.change_font_size)
        options_menu.addAction(font_size_action)

        underline_color_action = QAction("Change Spell Check Underline Color...", self)
        underline_color_action.triggered.connect(self.change_underline_color)
        options_menu.addAction(underline_color_action)

        self.theme_action = QAction("Switch to Light Theme", self)
        self.theme_action.triggered.connect(self.toggle_theme)
        options_menu.addAction(self.theme_action)

        load_glossary_action = QAction("Load Glossary...", self)
        load_glossary_action.triggered.connect(self.browse_glossary)
        options_menu.addAction(load_glossary_action)

        self.propagate_action = QAction("Propagate to Identical Segments", self)
        self.propagate_action.setCheckable(True)
        self.propagate_action.setChecked(self.xconfig['settings'].get('propagate_identical', True))
        self.propagate_action.triggered.connect(self.toggle_propagate_identical)
        options_menu.addAction(self.propagate_action)

        ai_toolbar = self.addToolBar("AI Provider")
        ai_toolbar.setMovable(False)
        ai_toolbar.addWidget(QLabel("  AI: "))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(AITranslationThread.PROVIDERS)
        self.provider_combo.setCurrentText(self.ai_provider)
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        ai_toolbar.addWidget(self.provider_combo)

        ai_toolbar.addWidget(QLabel("  Context: "))
        self.context_combo = QComboBox()
        self.context_combo.setEditable(True)
        self.context_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.context_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.context_combo.lineEdit().setPlaceholderText("Additional context for translation prompt…")
        ai_toolbar.addWidget(self.context_combo)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Filter bar
        filter_bar = QWidget()
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(4, 2, 4, 2)
        filter_layout.addWidget(QLabel("Source:"))
        self.filter_source = QLineEdit()
        self.filter_source.setPlaceholderText("Filter source…")
        self.filter_source.returnPressed.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_source)
        filter_layout.addWidget(QLabel("Target:"))
        self.filter_target = QLineEdit()
        self.filter_target.setPlaceholderText("Filter target…")
        self.filter_target.returnPressed.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_target)
        self.filter_logic = QComboBox()
        self.filter_logic.addItems(["AND", "OR"])
        filter_layout.addWidget(self.filter_logic)
        self.filter_regex = QCheckBox("Regex")
        filter_layout.addWidget(self.filter_regex)
        btn_filter = QPushButton("🔍")
        btn_filter.setToolTip("Apply filter")
        btn_filter.clicked.connect(self.apply_filter)
        filter_layout.addWidget(btn_filter)
        btn_clear = QPushButton("✕")
        btn_clear.setToolTip("Clear filter")
        btn_clear.clicked.connect(self.clear_filter)
        filter_layout.addWidget(btn_clear)
        filter_layout.addStretch()
        main_layout.addWidget(filter_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.table = QTableWidget()
        self.table.setColumnCount(5)  # Add column for File
        self.table.setHorizontalHeaderLabels(["ID", "File", "Source", "Target", "Status"])
        self.table.setItemDelegateForColumn(2, RichTextDelegate(self))  # Source is now column 2
        self.table.setItemDelegateForColumn(3, RichTextDelegate(self))  # Target is now column 3
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Source
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Target
        self.table.setColumnWidth(1, 28)  # File column — icon only
        self.table.setWordWrap(True)
        # Fixed mode with lazy per-row sizing: _resize_visible_rows() sizes only viewport rows on demand.
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.verticalHeader().hide()
        self.table.verticalScrollBar().valueChanged.connect(self._resize_visible_rows)
        
        # Enable immediate editing - CurrentChanged opens editor when you select a different cell
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.CurrentChanged |   # Open editor when cell selection changes
            QAbstractItemView.EditTrigger.SelectedClicked |  # Single click on already-selected cell
            QAbstractItemView.EditTrigger.AnyKeyPressed |    # Any key starts editing
            QAbstractItemView.EditTrigger.EditKeyPressed     # F2 or Enter starts editing
        )
        
        self.table.itemChanged.connect(self.on_item_changed)
        self.table.currentCellChanged.connect(self.on_cell_changed)
        splitter.addWidget(self.table)
        
        self.tm_list = QListWidget()
        self.tm_list.itemDoubleClicked.connect(self.insert_tm_match)
        self.tm_list.itemClicked.connect(self.on_list_item_clicked)
        splitter.addWidget(self.tm_list)
        
        splitter.setStretchFactor(0, 4)
        main_layout.addWidget(splitter, stretch=1)

    def _default_xconfig(self) -> dict:
        return {
            "api_keys": {
                "ANTHROPIC_API_KEY": "",
                "GOOGLE_API_KEY": "",
                "OPENAI_API_KEY": "",
                "DEEPL_API_KEY": "",
            },
            "settings": {
                "font_size": 10,
                "underline_color": {"r": 57, "g": 255, "b": 20},
                "ai_provider": "Claude",
                "glossary_file": "",
                "propagate_identical": True,
            },
            "recent_files": [],
            "contexts": [],
        }

    def load_xconfig(self):
        if not XCONFIG_PATH.exists():
            self.xconfig = self._migrate_to_xconfig()
            self.save_xconfig()
            self._delete_old_settings_files()
        else:
            try:
                with open(XCONFIG_PATH, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
            except Exception:
                loaded = {}
            cfg = self._default_xconfig()
            for section in cfg:
                if section in loaded:
                    if isinstance(cfg[section], dict):
                        cfg[section].update(loaded[section])
                    else:
                        cfg[section] = loaded[section]
            self.xconfig = cfg

        self.font_size = self.xconfig['settings'].get('font_size', 10)
        uc = self.xconfig['settings'].get('underline_color', {'r': 57, 'g': 255, 'b': 20})
        self.underline_color = QColor(uc['r'], uc['g'], uc['b'])
        self.recent_files = [f for f in self.xconfig.get('recent_files', []) if Path(f).exists()]

    def save_xconfig(self):
        try:
            tmp = XCONFIG_PATH.with_suffix('.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.xconfig, f, ensure_ascii=False, indent=2)
            tmp.replace(XCONFIG_PATH)
        except Exception:
            pass

    def _migrate_to_xconfig(self) -> dict:
        cfg = self._default_xconfig()

        old_font = Path.home() / ".xliff_editor_font.json"
        if old_font.exists():
            try:
                cfg['settings']['font_size'] = json.loads(old_font.read_text())['font_size']
            except Exception: pass

        old_color = Path.home() / ".xliff_editor_underline_color.json"
        if old_color.exists():
            try:
                d = json.loads(old_color.read_text())
                cfg['settings']['underline_color'] = {'r': d['r'], 'g': d['g'], 'b': d['b']}
            except Exception: pass

        old_provider = Path.home() / ".xliff_editor_ai_provider.json"
        if old_provider.exists():
            try:
                cfg['settings']['ai_provider'] = json.loads(old_provider.read_text()).get('provider', 'Claude')
            except Exception: pass

        old_recent = Path.home() / ".xliff_editor_recent.json"
        if old_recent.exists():
            try:
                cfg['recent_files'] = json.loads(old_recent.read_text())
            except Exception: pass

        old_contexts = Path.home() / ".xliff_editor_contexts.json"
        if old_contexts.exists():
            try:
                cfg['contexts'] = json.loads(old_contexts.read_text())
            except Exception: pass

        old_config = Path.home() / "config.json"
        if old_config.exists():
            try:
                d = json.loads(old_config.read_text())
                for key in ('ANTHROPIC_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY', 'DEEPL_API_KEY'):
                    if d.get(key):
                        cfg['api_keys'][key] = d[key]
                if not cfg['api_keys']['GOOGLE_API_KEY'] and d.get('GEMINI_API_KEY'):
                    cfg['api_keys']['GOOGLE_API_KEY'] = d['GEMINI_API_KEY']
                if d.get('glossary_file'):
                    cfg['settings']['glossary_file'] = d['glossary_file']
            except Exception: pass

        return cfg

    def _delete_old_settings_files(self):
        for name in (
            ".xliff_editor_font.json",
            ".xliff_editor_underline_color.json",
            ".xliff_editor_ai_provider.json",
            ".xliff_editor_recent.json",
            ".xliff_editor_contexts.json",
        ):
            p = Path.home() / name
            try:
                p.unlink(missing_ok=True)
            except Exception: pass

    def add_recent_file(self, filepath):
        """Add a file to the recent files list"""
        # Remove if already in list
        if filepath in self.recent_files:
            self.recent_files.remove(filepath)
        
        # Add to front of list
        self.recent_files.insert(0, filepath)
        
        # Limit to max_recent_files
        self.recent_files = self.recent_files[:self.max_recent_files]
        
        # Save and update menu
        self.xconfig['recent_files'] = self.recent_files
        self.save_xconfig()
        self.update_recent_files_menu()
    
    def update_recent_files_menu(self):
        """Update the Open Recent submenu with current recent files"""
        self.recent_menu.clear()
        
        if not self.recent_files:
            # No recent files
            action = QAction("(No recent files)", self)
            action.setEnabled(False)
            self.recent_menu.addAction(action)
        else:
            # Add each recent file
            for filepath in self.recent_files:
                # Show just the filename in menu, but keep full path
                filename = Path(filepath).name
                action = QAction(filename, self)
                action.setToolTip(filepath)  # Show full path as tooltip
                action.triggered.connect(lambda checked, f=filepath: self.open_recent_file(f))
                self.recent_menu.addAction(action)
            
            # Add separator and clear option
            self.recent_menu.addSeparator()
            clear_action = QAction("Clear Recent Files", self)
            clear_action.triggered.connect(self.clear_recent_files)
            self.recent_menu.addAction(clear_action)
    
    def open_recent_file(self, filepath):
        """Open a file from the recent files list"""
        if not Path(filepath).exists():
            QMessageBox.warning(self, "File Not Found", 
                              f"The file no longer exists:\n{filepath}")
            # Remove from recent files
            self.recent_files.remove(filepath)
            self.xconfig['recent_files'] = self.recent_files
            self.save_xconfig()
            self.update_recent_files_menu()
            return
        
        # Check if there are unsaved changes
        if self.is_modified:
            reply = QMessageBox.question(self, "Save?", 
                                        "Save changes to current file before opening?",
                                        QMessageBox.StandardButton.Yes | 
                                        QMessageBox.StandardButton.No | 
                                        QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Yes:
                self.save_xliff()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        
        # Open the file using the regular open mechanism
        self.open_xliff_file(filepath)
    
    def clear_recent_files(self):
        """Clear the recent files list"""
        self.recent_files = []
        self.xconfig['recent_files'] = self.recent_files
        self.save_xconfig()
        self.update_recent_files_menu()

    def on_provider_changed(self, provider):
        self.ai_provider = provider
        self.xconfig['settings']['ai_provider'] = provider
        self.save_xconfig()

    def load_glossary(self, path=None):
        """Load glossary from a tab-delimited file (source TAB target, one pair per line)."""
        if path is None:
            path = self.xconfig['settings'].get('glossary_file') or str(Path.home() / 'xliff_editor_glossary.tsv')
        path = Path(path).expanduser()
        if not path.exists():
            return
        glossary = {}
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n')
                if '\t' in line:
                    src, _, tgt = line.partition('\t')
                    if src.strip():
                        glossary[src.strip()] = tgt.strip()
        self.glossary = glossary

    def add_context_to_history(self, text):
        """Add text to context history (most-recent first, no duplicates)."""
        text = text.strip()
        if not text:
            return
        idx = self.context_combo.findText(text)
        if idx >= 0:
            self.context_combo.removeItem(idx)
        self.context_combo.insertItem(0, text)
        self.context_combo.setCurrentIndex(0)
        self.xconfig['contexts'] = [self.context_combo.itemText(i) for i in range(self.context_combo.count())]
        self.save_xconfig()

    def browse_glossary(self):
        """Open a file dialog to select a glossary TSV file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Glossary", str(Path.home()),
            "Tab-separated files (*.tsv *.txt);;All files (*)"
        )
        if path:
            self.load_glossary(path)
            self.xconfig['settings']['glossary_file'] = path
            self.save_xconfig()
            QMessageBox.information(
                self, "Glossary Loaded",
                f"Loaded {len(self.glossary)} term(s) from:\n{path}"
            )

    def get_ai_key(self):
        keys = self.xconfig.get('api_keys', {})
        if self.ai_provider == 'Claude':
            return keys.get('ANTHROPIC_API_KEY')
        elif self.ai_provider == 'Gemini':
            return keys.get('GOOGLE_API_KEY')
        elif self.ai_provider == 'OpenAI':
            return keys.get('OPENAI_API_KEY')
        elif self.ai_provider == 'DeepL':
            return keys.get('DEEPL_API_KEY')
        return None

    def _key_config_name(self):
        return {
            'Claude': 'ANTHROPIC_API_KEY',
            'Gemini': 'GOOGLE_API_KEY',
            'OpenAI': 'OPENAI_API_KEY',
            'DeepL': 'DEEPL_API_KEY',
        }.get(self.ai_provider, 'API_KEY')

    def change_font_size(self):
        """Show dialog to change font size"""
        size, ok = QInputDialog.getInt(
            self,
            "Change Font Size",
            "Enter font size (6-24):",
            value=self.font_size,
            min=6,
            max=24,
            step=1
        )

        if ok:
            self.font_size = size
            self.xconfig['settings']['font_size'] = size
            self.save_xconfig()
            self.apply_font_size()

    def change_underline_color(self):
        """Show dialog to change spell check underline color"""
        color = QColorDialog.getColor(
            self.underline_color,
            self,
            "Choose Spell Check Underline Color"
        )

        if color.isValid():
            self.underline_color = color
            self.xconfig['settings']['underline_color'] = {
                'r': color.red(), 'g': color.green(), 'b': color.blue()
            }
            self.save_xconfig()

            self._propagate_underline_color(self.current_underline_color)

            QMessageBox.information(self, "Color Changed",
                                  f"Spell check underline color updated to RGB({color.red()}, {color.green()}, {color.blue()}).\n\n"
                                  "New editors will use this color automatically.")
    
    def apply_font_size(self):
        """Apply the current font size to all widgets"""
        font = QFont()
        font.setPointSize(self.font_size)
        
        # Apply to application (menus)
        QApplication.instance().setFont(font)
        
        # Apply to table
        self.table.setFont(font)
        
        # Apply to TM list
        self.tm_list.setFont(font)
        
        # Force table to refresh with new font
        self.table.resizeRowsToContents()

    def detect_system_theme(self) -> str:
        lightness = QApplication.palette().color(QPalette.ColorRole.Window).lightness()
        return "light" if lightness > 127 else "dark"

    @property
    def current_underline_color(self) -> QColor:
        if getattr(self, 'current_theme', 'dark') == 'light':
            return QColor(255, 0, 0)
        return self.underline_color

    def apply_theme(self, theme: str):
        self.current_theme = theme
        if theme == "dark":
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            QApplication.instance().setPalette(palette)
            underline = self.underline_color
        else:
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(233, 233, 233))
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
            QApplication.instance().setPalette(palette)
            underline = QColor(255, 0, 0)
        self._propagate_underline_color(underline)
        self._update_locked_segment_colors()
        if hasattr(self, 'theme_action'):
            self.theme_action.setText(
                "Switch to Light Theme" if theme == "dark" else "Switch to Dark Theme"
            )

    def _propagate_underline_color(self, color: QColor):
        for row in range(self.table.rowCount()):
            editor = self.table.cellWidget(row, 3)
            if isinstance(editor, TagProtectedTextEdit):
                editor.set_underline_color(color)

    def _update_locked_segment_colors(self):
        if self.current_theme == "dark":
            bg = QColor(50, 50, 50)
            fg = QColor(150, 150, 150)
        else:
            bg = QColor(210, 210, 210)
            fg = QColor(100, 100, 100)
        for row in range(self.table.rowCount()):
            seg = self.segments[row] if row < len(self.segments) else None
            if seg and seg.get('locked', False):
                for col in (3, 4):
                    item = self.table.item(row, col)
                    if item:
                        item.setBackground(bg)
                        item.setForeground(fg)

    def toggle_theme(self):
        self.apply_theme("light" if self.current_theme == "dark" else "dark")

    def toggle_propagate_identical(self):
        self.xconfig['settings']['propagate_identical'] = self.propagate_action.isChecked()
        self.save_xconfig()

    def _propagate_to_identical(self, source_text: str, target_text: str, skip_row: int) -> int:
        if not self.xconfig['settings'].get('propagate_identical', True):
            return 0
        if not target_text:
            return 0
        count = 0
        self.table.itemChanged.disconnect()
        for r, seg in enumerate(self.segments):
            if r == skip_row or seg.get('locked', False):
                continue
            if seg['source'] == source_text:
                seg['target'] = target_text
                item = self.table.item(r, 3)
                if item:
                    item.setText(target_text)
                count += 1
        self.table.itemChanged.connect(self.on_item_changed)
        return count

    # --- Tag Handling Logic ---

    def parse_content_with_tags(self, element):
        """Converts XLIFF XML content into text with simplified <1> tokens."""
        if not element: return "", {}
        
        text_parts = []
        tag_map = {}
        tag_counter = 1

        for child in element.children:
            if isinstance(child, NavigableString):
                text_parts.append(str(child))
            elif isinstance(child, Tag):
                num = tag_counter
                tag_counter += 1
                
                # Store original data
                tag_info = {
                    'name': child.name,
                    'attrs': child.attrs,
                    'paired': (child.name == 'pc')
                }
                tag_map[num] = tag_info
                
                if tag_info['paired']:
                    inner_text, inner_map = self.parse_content_with_tags(child)
                    # Merge inner maps if any (though XLIFF 2.2 usually flat)
                    for k, v in inner_map.items():
                        tag_map[tag_counter] = v
                        tag_counter += 1
                    text_parts.append(f"<{num}>{inner_text}</{num}>")
                else:
                    text_parts.append(f"<{num}/>")
        
        return "".join(text_parts), tag_map

    def serialize_to_xml(self, text, tag_map, soup):
        """Converts grid text with <1> tokens back into XLIFF XML nodes."""
        # Sort keys descending to avoid replacing <10> with <1>0
        sorted_keys = sorted(tag_map.keys(), reverse=True)
        
        current_xml = text
        for k in sorted_keys:
            info = tag_map[k]
            if info['paired']:
                # Replace <k> and </k> for paired tags
                # Using temp placeholders to avoid collision
                attr_str = " ".join([f'{a}="{v}"' for a, v in info['attrs'].items()])
                if attr_str:
                    attr_str = " " + attr_str  # Add space before attributes
                current_xml = current_xml.replace(f"<{k}>", f"TEMP_START_{k}")
                current_xml = current_xml.replace(f"</{k}>", f"TEMP_END_{k}")
                current_xml = current_xml.replace(f"TEMP_START_{k}", f'<{info["name"]}{attr_str}>')
                current_xml = current_xml.replace(f"TEMP_END_{k}", f'</{info["name"]}>')
            else:
                # Replace <k/> for unpaired tags
                attr_str = " ".join([f'{a}="{v}"' for a, v in info['attrs'].items()])
                if attr_str:
                    attr_str = " " + attr_str  # Add space before attributes
                current_xml = current_xml.replace(f"<{k}/>", f'<{info["name"]}{attr_str}/>')
        
        # Create a temporary soup to parse this string back into a set of nodes
        try:
            fragment = BeautifulSoup(f"<root>{current_xml}</root>", 'xml')
            return fragment.root.contents
        except:
            return [soup.new_string(text)]

    # --- UI Actions ---

    def open_xliff(self):
        """Open XLIFF via file dialog"""
        file_name, _ = QFileDialog.getOpenFileName(self, "Open XLIFF", "", "XLIFF Files (*.xliff *.xlf)")
        if not file_name:
            return
        
        self.open_xliff_file(file_name)
    
    def open_xliff_file(self, file_name):
        """Open a specific XLIFF file (used by both open dialog and recent files)"""
        # Create progress dialog
        self.xliff_progress = QProgressDialog("Loading XLIFF file...", "Cancel", 0, 100, self)
        self.xliff_progress.setWindowTitle("Loading XLIFF")
        self.xliff_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.xliff_progress.setCancelButton(None)
        self.xliff_progress.show()
        
        # Start loading thread
        self.xliff_thread = XLIFFLoadThread(file_name, self.parse_content_with_tags)
        self.xliff_thread.progress.connect(self.on_xliff_progress)
        self.xliff_thread.finished.connect(self.on_xliff_loaded)
        self.xliff_thread.error.connect(self.on_xliff_error)
        self.xliff_thread.start()
    
    def on_xliff_progress(self, current, total):
        if total > 0:
            progress = int((current / total) * 100)
            self.xliff_progress.setValue(progress)
            self.xliff_progress.setLabelText(f"Loading XLIFF file... ({current}/{total} segments)")
    
    def on_xliff_loaded(self, xliff_soup, segments, filepath):
        self.xliff_soup = xliff_soup
        self.segments = segments
        self.xliff_file = filepath
        
        # Add to recent files
        self.add_recent_file(filepath)
        
        # Extract language information from the XLIFF root element
        xliff_root = self.xliff_soup.find('xliff')
        if xliff_root:
            self.src_lang = xliff_root.get('srcLang', 'unknown')
            self.trg_lang = xliff_root.get('trgLang', None)
        else:
            self.src_lang = 'unknown'
            self.trg_lang = None
        
        self.populate_table()
        self.update_window_title()
        self.xliff_progress.close()
        self.is_modified = False
        
        # Show language info if target language is missing
        if not self.trg_lang:
            QMessageBox.information(self, "No Target Language", 
                                  f"Source language: {self.src_lang}\n\n"
                                  "No target language specified in XLIFF file.\n"
                                  "You can set it using File → Set Target Language (Ctrl+L)")
    
    def update_window_title(self):
        """Update window title with file name and language info"""
        title = f"XLIFF Editor - {self.xliff_file}"
        if self.src_lang and self.trg_lang:
            title += f" [{self.src_lang} → {self.trg_lang}]"
        elif self.src_lang:
            title += f" [{self.src_lang} → ?]"
        self.setWindowTitle(title)
    
    def on_xliff_error(self, error_msg):
        self.xliff_progress.close()
        QMessageBox.critical(self, "Error", f"Open failed: {error_msg}")

    def populate_table(self):
        self.table.itemChanged.disconnect()
        self.table.setRowCount(len(self.segments))
        for row, seg in enumerate(self.segments):
            is_locked = seg.get('locked', False)
            
            # Column 0: ID (row number) with padlock for locked segments
            id_text = str(row + 1)
            if is_locked:
                id_text = "🔒 " + id_text  # Add padlock emoji
            id_item = QTableWidgetItem(id_text)
            id_item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # Read-only
            self.table.setItem(row, 0, id_item)
            
            # Column 1: File ID — show placeholder, full name in tooltip
            file_id = seg.get('file_id', 'unknown')
            file_item = QTableWidgetItem("📄")
            file_item.setToolTip(file_id)
            file_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            file_item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # Read-only
            self.table.setItem(row, 1, file_item)
            
            # Column 2: Source
            source_item = QTableWidgetItem(seg['source'])
            source_item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # Read-only
            self.table.setItem(row, 2, source_item)
            
            # Column 3: Target
            target_item = QTableWidgetItem(seg['target'])
            if is_locked:
                # Make locked segments read-only
                target_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                # Use darker background to match theme (slightly lighter than base)
                target_item.setBackground(QColor(50, 50, 50))
                # Make text gray to indicate locked status
                target_item.setForeground(QColor(150, 150, 150))
            self.table.setItem(row, 3, target_item)
            
            # Column 4: Status
            status_item = QTableWidgetItem(seg['state'])
            if is_locked:
                # Make status read-only for locked segments
                status_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                # Use darker background to match theme
                status_item.setBackground(QColor(50, 50, 50))
                # Make text gray to indicate locked status
                status_item.setForeground(QColor(150, 150, 150))
            self.table.setItem(row, 4, status_item)
            
        self.table.itemChanged.connect(self.on_item_changed)
        self.clear_filter()

    def apply_filter(self):
        src_text = self.filter_source.text()
        trg_text = self.filter_target.text()
        use_regex = self.filter_regex.isChecked()
        use_and = self.filter_logic.currentText() == "AND"

        try:
            src_pat = re.compile(src_text, re.IGNORECASE) if (src_text and use_regex) else (src_text or None)
            trg_pat = re.compile(trg_text, re.IGNORECASE) if (trg_text and use_regex) else (trg_text or None)
        except re.error as e:
            QMessageBox.warning(self, "Invalid Regex", str(e))
            return

        for row in range(self.table.rowCount()):
            src = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
            trg = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
            self.table.setRowHidden(row, not _filter_matches(src, trg, src_pat, trg_pat, use_and))

    def clear_filter(self):
        self.filter_source.clear()
        self.filter_target.clear()
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)

    def _resize_visible_rows(self):
        """Resize only the rows currently visible in the viewport to their content height."""
        vp = self.table.viewport()
        first = self.table.rowAt(0)
        last = self.table.rowAt(vp.height() - 1)
        if first < 0:
            return
        if last < 0:
            # Content doesn't fill the viewport; resize to the actual last row.
            last = self.table.rowCount() - 1
        for row in range(first, last + 1):
            if not self.table.isRowHidden(row):
                self.table.resizeRowToContents(row)

    def insert_next_tag(self):
        """Finds the next tag in source not used in target and inserts it."""
        if self.current_row < 0: return
        
        row = self.current_row
        seg = self.segments[row]
        target_item = self.table.item(row, 3)  # Column 3 is now Target
        
        # Check if we're currently editing the cell
        current_editor = None
        if self.table.currentRow() == row and self.table.currentColumn() == 3:  # Column 3 is Target
            # Try to get the active editor
            index = self.table.model().index(row, 3)  # Column 3 is Target
            current_editor = self.table.indexWidget(index)
            if not current_editor:
                # Check if there's a persistent editor
                for i in range(self.table.viewport().children().__len__()):
                    widget = self.table.itemDelegate(index).parent()
                # Try getting editor differently
                current_editor = self.table.cellWidget(row, 3)  # Column 3 is Target
        
        # If we're in edit mode, try to find the editor
        if not current_editor:
            # Look for TagProtectedTextEdit in viewport children
            for child in self.table.viewport().children():
                if isinstance(child, TagProtectedTextEdit) and child.isVisible():
                    current_editor = child
                    break
        
        # Get current target text
        if current_editor and isinstance(current_editor, TagProtectedTextEdit):
            current_target = current_editor.toPlainText()
            cursor = current_editor.textCursor()
            cursor_pos = cursor.position()
        else:
            current_target = target_item.text()
            cursor_pos = len(current_target)  # Append at end if not editing
        
        # Find all tags in source
        source_indices = sorted(seg['tag_map'].keys())
        
        tag_to_insert = None
        for i in source_indices:
            info = seg['tag_map'][i]
            if info['paired']:
                # For paired tags, only insert opening tag if not present
                if f"<{i}>" not in current_target:
                    tag_to_insert = f"<{i}>"
                    break
                # Check if closing tag is missing
                elif f"</{i}>" not in current_target:
                    tag_to_insert = f"</{i}>"
                    break
            else:
                if f"<{i}/>" not in current_target:
                    tag_to_insert = f"<{i}/>"
                    break
        
        if not tag_to_insert:
            return  # No tags to insert
        
        # Insert the tag
        if current_editor and isinstance(current_editor, TagProtectedTextEdit):
            # Insert at cursor position in the editor
            cursor = current_editor.textCursor()
            cursor.insertText(tag_to_insert)
            current_editor.setTextCursor(cursor)
            # Manually trigger tag detection
            current_editor.detect_and_protect_tags()
        else:
            # Not editing, just append to the end
            target_item.setText(current_target + tag_to_insert)

    def save_xliff(self):
        if not self.xliff_soup: return
        
        # Sync all table data back to segments before saving
        # This ensures we capture any recent edits
        for row in range(len(self.segments)):
            target_item = self.table.item(row, 3)  # Column 3 is now Target
            if target_item:
                self.segments[row]['target'] = target_item.text()
            state_item = self.table.item(row, 4)  # Column 4 is now Status
            if state_item:
                self.segments[row]['state'] = state_item.text()
        
        for seg in self.segments:
            node = seg['segment_node']
            tgt_node = node.find('target')
            if not tgt_node:
                tgt_node = self.xliff_soup.new_tag('target')
                tgt_node['xml:space'] = 'preserve'
                node.append(tgt_node)
            
            # Clear existing content
            tgt_node.clear()
            
            # Use safe state logic
            target_str = seg['target']
            state = seg['state']
            if not target_str.strip():
                state = 'initial'
            
            node['state'] = state
            
            # Parse text with placeholders back to XML nodes
            new_contents = self.serialize_to_xml(target_str, seg['tag_map'], self.xliff_soup)
            
            # CRITICAL: Iterate over a copy of the list because appending removes from source
            for c in list(new_contents):
                tgt_node.append(c)

        try:
            with open(self.xliff_file, 'w', encoding='utf-8') as f:
                f.write(str(self.xliff_soup))
            self.is_modified = False
            QMessageBox.information(self, "Saved", "XLIFF saved with tags preserved.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed: {e}")

    def save_xliff_as(self):
        """Save XLIFF file with a new name"""
        if not self.xliff_soup:
            QMessageBox.warning(self, "No File", "Please open an XLIFF file first.")
            return
        
        # Get new file name from user
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save XLIFF As",
            self.xliff_file if self.xliff_file else "",
            "XLIFF Files (*.xliff *.xlf);;All Files (*)"
        )
        
        if not file_name:
            return  # User cancelled
        
        # Save the current file name
        old_file = self.xliff_file
        
        # Update to new file name
        self.xliff_file = file_name
        
        # Call the regular save method
        # Sync all table data back to segments before saving
        for row in range(len(self.segments)):
            target_item = self.table.item(row, 3)  # Column 3 is now Target
            if target_item:
                self.segments[row]['target'] = target_item.text()
            state_item = self.table.item(row, 4)  # Column 4 is now Status
            if state_item:
                self.segments[row]['state'] = state_item.text()
        
        for seg in self.segments:
            node = seg['segment_node']
            tgt_node = node.find('target')
            if not tgt_node:
                tgt_node = self.xliff_soup.new_tag('target')
                tgt_node['xml:space'] = 'preserve'
                node.append(tgt_node)
            
            # Clear existing content
            tgt_node.clear()
            
            # Use safe state logic
            target_str = seg['target']
            state = seg['state']
            if not target_str.strip():
                state = 'initial'
            
            node['state'] = state
            
            # Parse text with placeholders back to XML nodes
            new_contents = self.serialize_to_xml(target_str, seg['tag_map'], self.xliff_soup)
            
            # CRITICAL: Iterate over a copy of the list because appending removes from source
            for c in list(new_contents):
                tgt_node.append(c)

        try:
            with open(self.xliff_file, 'w', encoding='utf-8') as f:
                f.write(str(self.xliff_soup))
            self.is_modified = False
            self.update_window_title()
            QMessageBox.information(self, "Saved", f"XLIFF saved as:\n{file_name}")
        except Exception as e:
            # Restore old file name if save failed
            self.xliff_file = old_file
            QMessageBox.critical(self, "Error", f"Save failed: {e}")

    # --- Standard Handlers (Updated for Mod) ---

    def on_item_changed(self, item):
        if item.column() == 3:  # Column 3 is now Target
            row = item.row()
            val = item.text()
            self.segments[row]['target'] = val
            self.is_modified = True
            count = self._propagate_to_identical(self.segments[row]['source'], val, row)
            if count:
                self.statusBar().showMessage(f"Propagated to {count} identical segment(s).", 3000)

    def on_cell_changed(self, row, col, p_row, p_col):
        if row >= 0:
            self.current_row = row
            if not self.segments[row]['target']:
                self.search_tm(self.segments[row]['source'])

    def set_target_language(self):
        """Allow user to set or change the target language"""
        if not self.xliff_soup:
            QMessageBox.warning(self, "No File", "Please open an XLIFF file first.")
            return
        
        # Common language codes for suggestions
        common_langs = [
            "pl-PL (Polish - Poland)",
            "de-DE (German - Germany)",
            "fr-FR (French - France)",
            "es-ES (Spanish - Spain)",
            "it-IT (Italian - Italy)",
            "pt-BR (Portuguese - Brazil)",
            "ja-JP (Japanese - Japan)",
            "zh-CN (Chinese - China)",
            "ru-RU (Russian - Russia)",
            "ar-SA (Arabic - Saudi Arabia)",
        ]
        
        current_info = f"Current source language: {self.src_lang}\n"
        current_info += f"Current target language: {self.trg_lang if self.trg_lang else 'Not set'}\n\n"
        current_info += "Enter target language code (e.g., pl-PL, de-DE, fr-FR):"
        
        lang_code, ok = QInputDialog.getText(
            self, 
            "Set Target Language",
            current_info,
            text=self.trg_lang if self.trg_lang else ""
        )
        
        if ok and lang_code.strip():
            lang_code = lang_code.strip()
            
            # Basic validation - should be in format xx-XX or just xx
            if not (2 <= len(lang_code) <= 10):
                QMessageBox.warning(self, "Invalid Format", 
                                  "Language code should be 2-10 characters (e.g., pl-PL, en-US)")
                return
            
            # Update the XLIFF root element
            xliff_root = self.xliff_soup.find('xliff')
            if xliff_root:
                xliff_root['trgLang'] = lang_code
                self.trg_lang = lang_code
                self.is_modified = True
                self.update_window_title()
                QMessageBox.information(self, "Target Language Set", 
                                      f"Target language set to: {lang_code}")
            else:
                QMessageBox.critical(self, "Error", "Could not find XLIFF root element")

    def edit_languages(self):
        """Allow user to edit both source and target languages"""
        if not self.xliff_soup:
            QMessageBox.warning(self, "No File", "Please open an XLIFF file first.")
            return
        
        # Create a custom dialog for editing both languages
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Languages")
        dialog.setModal(True)
        
        layout = QVBoxLayout()
        
        # Info label
        info_label = QLabel("Edit the source and target language codes for this XLIFF file.\n"
                           "Use BCP-47 format (e.g., en-US, pl-PL, de-DE)")
        layout.addWidget(info_label)
        
        # Form for language inputs
        form_layout = QFormLayout()
        
        src_input = QLineEdit()
        src_input.setText(self.src_lang if self.src_lang else "")
        src_input.setPlaceholderText("e.g., en-US")
        form_layout.addRow("Source Language:", src_input)
        
        trg_input = QLineEdit()
        trg_input.setText(self.trg_lang if self.trg_lang else "")
        trg_input.setPlaceholderText("e.g., pl-PL")
        form_layout.addRow("Target Language:", trg_input)
        
        layout.addLayout(form_layout)
        
        # Common languages hint
        hint_label = QLabel("\nCommon codes: en-US, pl-PL, de-DE, fr-FR, es-ES, it-IT, pt-BR, ja-JP, zh-CN, ru-RU")
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(hint_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Connect buttons
        ok_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        
        # Show dialog and process result
        if dialog.exec() == QDialog.DialogCode.Accepted:
            src_code = src_input.text().strip()
            trg_code = trg_input.text().strip()
            
            # Validate
            if not src_code:
                QMessageBox.warning(self, "Invalid Input", "Source language cannot be empty.")
                return
            
            if not (2 <= len(src_code) <= 10):
                QMessageBox.warning(self, "Invalid Format", 
                                  "Source language code should be 2-10 characters (e.g., en-US)")
                return
            
            if trg_code and not (2 <= len(trg_code) <= 10):
                QMessageBox.warning(self, "Invalid Format", 
                                  "Target language code should be 2-10 characters (e.g., pl-PL)")
                return
            
            # Update the XLIFF root element
            xliff_root = self.xliff_soup.find('xliff')
            if xliff_root:
                xliff_root['srcLang'] = src_code
                self.src_lang = src_code
                
                if trg_code:
                    xliff_root['trgLang'] = trg_code
                    self.trg_lang = trg_code
                elif 'trgLang' in xliff_root.attrs:
                    # Remove target language if empty
                    del xliff_root['trgLang']
                    self.trg_lang = None
                
                self.is_modified = True
                self.update_window_title()
                
                msg = f"Languages updated:\nSource: {src_code}"
                if trg_code:
                    msg += f"\nTarget: {trg_code}"
                else:
                    msg += "\nTarget: (not set)"
                QMessageBox.information(self, "Languages Updated", msg)
            else:
                QMessageBox.critical(self, "Error", "Could not find XLIFF root element")

    def close_xliff(self):
        if self.is_modified:
            if QMessageBox.question(self, "Save?", "Save changes?") == QMessageBox.StandardButton.Yes:
                self.save_xliff()
        self.table.setRowCount(0)
        self.clear_filter()
        self.segments = []
        self.xliff_file = None
        self.xliff_soup = None
        self.src_lang = None
        self.trg_lang = None
        self.setWindowTitle("Xliff 2 Editor")

    def closeEvent(self, event):
        """Override close event to ask about saving modified files"""
        # Commit active editor before checking - more reliable than clearFocus()
        if self.table.state() == QAbstractItemView.State.EditingState:
            self.table.setCurrentIndex(QModelIndex())
        QApplication.processEvents()
        
        if self.is_modified:
            msgBox = QMessageBox(self)
            msgBox.setWindowTitle("Save Changes?")
            msgBox.setText("The document has been modified.")
            msgBox.setInformativeText("Do you want to save your changes?")
            msgBox.setStandardButtons(
                QMessageBox.StandardButton.Save | 
                QMessageBox.StandardButton.Discard | 
                QMessageBox.StandardButton.Cancel
            )
            msgBox.setDefaultButton(QMessageBox.StandardButton.Save)
            
            reply = msgBox.exec()
            
            if reply == QMessageBox.StandardButton.Save:
                self.save_xliff()
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:  # Cancel
                event.ignore()
        else:
            event.accept()

    def load_tmx(self):
        path, _ = QFileDialog.getOpenFileName(self, "TMX", "", "*.tmx")
        if not path:
            return
        
        # Create progress dialog (hidden initially)
        self.tmx_progress = QProgressDialog("Loading TMX file...", "Cancel", 0, 0, self)
        self.tmx_progress.setWindowTitle("Loading TMX")
        self.tmx_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.tmx_progress.setMinimumDuration(5000)  # Show after 5 seconds
        self.tmx_progress.setCancelButton(None)  # No cancel button for now
        
        # Start loading thread
        self.tmx_thread = TMXLoadThread(path)
        self.tmx_thread.finished.connect(self.on_tmx_loaded)
        self.tmx_thread.error.connect(self.on_tmx_error)
        self.tmx_thread.start()
        
        # Show progress immediately if we expect it to take a while
        self.tmx_progress.show()
    
    def on_tmx_loaded(self, tmx_dict):
        self.tmx_data = tmx_dict
        self.tmx_progress.close()
        QMessageBox.information(self, "TMX Loaded", f"Loaded {len(tmx_dict)} translation units.")
    
    def on_tmx_error(self, error_msg):
        self.tmx_progress.close()
        QMessageBox.critical(self, "Error", f"Failed to load TMX: {error_msg}")

    def search_tm(self, text):
        self.tm_list.clear()

        # TM matches — sorted by score descending
        tm_hits = sorted(
            ((fuzz.ratio(text.lower(), s.lower()), s, t) for s, t in self.tmx_data.items()),
            reverse=True
        )
        for r, s, t in tm_hits:
            if r < 70:
                break
            item = QListWidgetItem(f"{r}% — {t}")
            item.setData(Qt.ItemDataRole.UserRole, {'type': 'tm', 'translation': t})
            self.tm_list.addItem(item)

        # Glossary matches
        if self.glossary:
            src_lower = text.lower()
            gmatches = [(k, v) for k, v in self.glossary.items() if k.lower() in src_lower]
            if gmatches:
                if tm_hits and tm_hits[0][0] >= 70:
                    sep = QListWidgetItem("── glossary ──")
                    sep.setFlags(Qt.ItemFlag.NoItemFlags)
                    sep.setForeground(QColor(120, 120, 120))
                    self.tm_list.addItem(sep)
                for k, v in gmatches:
                    item = QListWidgetItem(f"{k} — {v}")
                    item.setData(Qt.ItemDataRole.UserRole, {'type': 'glossary', 'translation': v})
                    self.tm_list.addItem(item)

    def insert_tm_match(self, item):
        """Double-click: overwrite target with TM match."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data.get('type') == 'tm' and self.current_row >= 0:
            self.table.item(self.current_row, 3).setText(data['translation'])

    def on_list_item_clicked(self, item):
        """Single-click: insert glossary translation at cursor (or append)."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'glossary' or self.current_row < 0:
            return
        translation = data['translation']
        editor = QApplication.focusWidget()
        if isinstance(editor, TagProtectedTextEdit):
            editor.insertPlainText(translation)
        else:
            current = self.segments[self.current_row].get('target', '')
            sep = ' ' if current and not current.endswith(' ') else ''
            self.table.item(self.current_row, 3).setText(current + sep + translation)

    def clear_current_target(self):
        if self.current_row >= 0:
            # Check if segment is locked
            if self.segments[self.current_row].get('locked', False):
                QMessageBox.warning(self, "Segment Locked", 
                                  "This segment is locked (translate=\"no\") and cannot be modified.")
                return
            
            self.table.item(self.current_row, 3).setText("")  # Column 3 is now Target
            self.table.item(self.current_row, 4).setText("initial")  # Column 4 is now Status

    def clear_all_targets(self):
        """Clear all target segments with a progress indicator"""
        if not self.segments:
            QMessageBox.warning(self, "No File", "Please open an XLIFF file first.")
            return
        
        # Confirm action
        visible_count = sum(
            1 for row in range(len(self.segments))
            if not self.table.isRowHidden(row)
        )
        filter_note = (
            f"\n\n(A filter is active — {len(self.segments) - visible_count} hidden rows will not be affected.)"
            if visible_count < len(self.segments) else ""
        )
        reply = QMessageBox.question(
            self,
            "Clear All Targets",
            f"This will clear {visible_count} target segment(s).\n\nAre you sure?{filter_note}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Show progress dialog
        progress = QProgressDialog("Clearing all targets...", "Cancel", 0, visible_count, self)
        progress.setWindowTitle("Clear All Targets")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        
        # Disconnect itemChanged to avoid triggering it for every cell
        self.table.itemChanged.disconnect()
        
        try:
            skipped_count = 0
            cleared_count = 0
            progress_value = 0
            for row in range(len(self.segments)):
                if progress.wasCanceled():
                    break

                # Skip hidden (filtered-out) segments
                if self.table.isRowHidden(row):
                    continue

                # Skip locked segments
                if self.segments[row].get('locked', False):
                    skipped_count += 1
                    continue

                # Clear target text and set state to initial
                self.table.item(row, 3).setText("")  # Column 3 is now Target
                self.table.item(row, 4).setText("initial")  # Column 4 is now Status
                self.segments[row]['target'] = ""
                self.segments[row]['state'] = "initial"
                cleared_count += 1

                # Update progress every 10 rows
                progress_value += 1
                if progress_value % 10 == 0 or progress_value == visible_count:
                    progress.setValue(progress_value)
                    QApplication.processEvents()  # Keep UI responsive

            progress.setValue(visible_count)
            self.is_modified = True

            if not progress.wasCanceled():
                msg = f"Cleared {cleared_count} target(s)."
                if skipped_count > 0:
                    msg += f"\n\nSkipped {skipped_count} locked segment(s)."
                QMessageBox.information(self, "Complete", msg)
        finally:
            # Reconnect itemChanged
            self.table.itemChanged.connect(self.on_item_changed)
            progress.close()

    def copy_source_to_target(self):
        """Copy the source text to the target for the current row, preserving tags"""
        if self.current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a segment first.")
            return
        
        # Check if segment is locked
        if self.segments[self.current_row].get('locked', False):
            QMessageBox.warning(self, "Segment Locked", 
                              "This segment is locked (translate=\"no\") and cannot be modified.")
            return
        
        row = self.current_row
        source_text = self.segments[row]['source']
        
        # Copy source to target
        self.table.item(row, 3).setText(source_text)  # Column 3 is now Target
        self.segments[row]['target'] = source_text
        self.is_modified = True

    def copy_all_sources_to_targets(self):
        """Copy all source texts to targets with a progress indicator"""
        if not self.segments:
            QMessageBox.warning(self, "No File", "Please open an XLIFF file first.")
            return

        # Count visible rows before confirmation dialog
        visible_count = sum(
            1 for row in range(len(self.segments))
            if not self.table.isRowHidden(row)
        )
        filter_note = f"\n\n(A filter is active — {len(self.segments) - visible_count} hidden rows will not be affected.)" if visible_count < len(self.segments) else ""

        # Confirm action
        reply = QMessageBox.question(
            self,
            "Copy All Sources to Targets",
            f"This will copy {visible_count} source segment(s) to their corresponding targets.\n\n"
            f"Existing target content will be overwritten.{filter_note}\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Show progress dialog
        progress = QProgressDialog("Copying sources to targets...", "Cancel", 0, visible_count, self)
        progress.setWindowTitle("Copy Sources to Targets")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        
        # Disconnect itemChanged to avoid triggering it for every cell
        self.table.itemChanged.disconnect()

        try:
            skipped_count = 0
            copied_count = 0
            for row in range(len(self.segments)):
                if progress.wasCanceled():
                    break

                # Skip hidden (filtered-out) and locked segments
                if self.table.isRowHidden(row):
                    continue
                if self.segments[row].get('locked', False):
                    skipped_count += 1
                    continue

                # Copy source to target (tags are already in the source text as <1>, <2/>, etc.)
                source_text = self.segments[row]['source']
                self.table.item(row, 3).setText(source_text)  # Column 3 is now Target
                self.segments[row]['target'] = source_text
                # Update progress every 10 rows
                copied_count += 1
                if copied_count % 10 == 0 or copied_count == visible_count:
                    progress.setValue(copied_count)
                    QApplication.processEvents()  # Keep UI responsive

            progress.setValue(visible_count)
            self.is_modified = True
            
            if not progress.wasCanceled():
                msg = f"Copied {copied_count} sources to targets."
                if skipped_count > 0:
                    msg += f"\n\nSkipped {skipped_count} locked segment(s)."
                QMessageBox.information(self, "Complete", msg)
        finally:
            # Reconnect itemChanged
            self.table.itemChanged.connect(self.on_item_changed)
            progress.close()

    def set_current_translated(self):
        if self.current_row >= 0:
            self.table.item(self.current_row, 4).setText("translated")  # Column 4 is now Status
            self.segments[self.current_row]['state'] = "translated"

    def ai_translate_current(self):
        """Translate the current segment using AI"""
        # Validate preconditions
        if self.current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a segment to translate.")
            return
        
        if not self.segments:
            QMessageBox.warning(self, "No File", "Please open an XLIFF file first.")
            return
        
        # Check if segment is locked
        if self.segments[self.current_row].get('locked', False):
            QMessageBox.warning(self, "Segment Locked", 
                              "This segment is locked (translate=\"no\") and cannot be modified.")
            return
        
        key = self.get_ai_key()
        if not key:
            QMessageBox.warning(self, "No API Key",
                              f"Please add your {self._key_config_name()} to XLIFF2Editor/xconfig.json.")
            return

        row = self.current_row
        src = self.segments[row]['source']

        if not src.strip():
            QMessageBox.warning(self, "Empty Source", "The source segment is empty.")
            return

        self.ai_progress = QProgressDialog("Translating segment...", "Cancel", 0, 1, self)
        self.ai_progress.setWindowTitle(f"AI Translation ({self.ai_provider})")
        self.ai_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.ai_progress.setValue(0)
        self.ai_progress.show()

        context = self.context_combo.currentText()
        self.add_context_to_history(context)
        self.ai_thread = AITranslationThread(
            self.ai_provider, key, [(row, src)],
            self.glossary,
            self.src_lang or '', self.trg_lang or '',
            context
        )
        self.ai_thread.segment_translated.connect(self.on_segment_translated)
        self.ai_thread.finished.connect(self.on_ai_finished)
        self.ai_thread.error.connect(self.on_ai_error)
        self.ai_thread.start()

    def ai_translate_all_initial(self):
        """Translate all segments with 'initial' status using AI"""
        if not self.segments:
            QMessageBox.warning(self, "No File", "Please open an XLIFF file first.")
            return
        
        key = self.get_ai_key()
        if not key:
            QMessageBox.warning(self, "No API Key",
                              f"Please add your {self._key_config_name()} to XLIFF2Editor/xconfig.json.")
            return

        to_tr = [(r, s['source']) for r, s in enumerate(self.segments)
                 if s['state'] == 'initial' and s['source'].strip()
                 and not s.get('locked', False) and not self.table.isRowHidden(r)]

        if not to_tr:
            QMessageBox.information(self, "Nothing to Translate",
                                  "All segments are already translated, locked, or have empty source text.")
            return

        self.ai_progress = QProgressDialog("Translating segments...", "Cancel", 0, len(to_tr), self)
        self.ai_progress.setWindowTitle(f"AI Translation ({self.ai_provider})")
        self.ai_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.ai_progress.setValue(0)

        context = self.context_combo.currentText()
        self.add_context_to_history(context)
        self.ai_thread = AITranslationThread(
            self.ai_provider, key, to_tr,
            self.glossary,
            self.src_lang or '', self.trg_lang or '',
            context
        )
        self.ai_thread.segment_translated.connect(self.on_segment_translated)
        self.ai_thread.progress.connect(self.on_ai_progress)
        self.ai_thread.finished.connect(self.on_ai_finished)
        self.ai_thread.error.connect(self.on_ai_error)
        self.ai_thread.start()

    def on_ai_progress(self, current, total):
        """Update AI translation progress"""
        if hasattr(self, 'ai_progress') and self.ai_progress:
            self.ai_progress.setValue(current)
            self.ai_progress.setLabelText(f"Translating segments... ({current}/{total})")

    def on_segment_translated(self, row, trans, status):
        """Handle a translated segment"""
        self.table.itemChanged.disconnect()
        self.segments[row]['target'] = trans
        self.segments[row]['state'] = 'initial'
        self.table.item(row, 3).setText(trans)  # Column 3 is now Target
        self.table.item(row, 4).setText('initial')  # Column 4 is now Status
        self.table.itemChanged.connect(self.on_item_changed)
        self.is_modified = True
        count = self._propagate_to_identical(self.segments[row]['source'], trans, row)
        if count:
            self.statusBar().showMessage(f"Propagated to {count} identical segment(s).", 3000)

    def on_ai_finished(self):
        """Handle AI translation completion"""
        if hasattr(self, 'ai_progress') and self.ai_progress:
            self.ai_progress.close()
        if self.ai_thread and len(self.ai_thread.segments_to_translate) > 1:
            QMessageBox.information(self, "Translation Complete", "AI translation finished successfully.")

    def on_ai_error(self, error_msg):
        """Handle AI translation error"""
        if hasattr(self, 'ai_progress') and self.ai_progress:
            self.ai_progress.close()
        QMessageBox.critical(self, "Translation Error", f"AI translation failed:\n\n{error_msg}")

    def cancel_ai_translation(self):
        if self.ai_thread:
            self.ai_thread.is_cancelled = True

    def move_to_external_screen(self):
        """If an external screen is connected, centre the window on it."""
        primary = QApplication.primaryScreen()
        external = next((s for s in QApplication.screens() if s is not primary), None)
        if external:
            geom = external.availableGeometry()
            x = geom.x() + (geom.width() - self.width()) // 2
            y = geom.y() + (geom.height() - self.height()) // 2
            self.move(x, y)

    def import_from_sdlxliff(self):
        """Import SDLXLIFF file(s) and convert to XLIFF 2.2"""
        try:
            # Import the converter module
            import sdlxliff_xliff22_converter as converter
        except ImportError:
            QMessageBox.critical(self, "Module Missing", 
                               "The sdlxliff_xliff22_converter.py module is not found.\n\n"
                               "Please ensure it's in the same directory as this editor.")
            return
        
        # Select SDLXLIFF file(s)
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "Select SDLXLIFF File(s)", 
            "", 
            "SDLXLIFF Files (*.sdlxliff);;All Files (*)"
        )
        
        if not file_paths:
            return
        
        # Ask for output location — default to first source file's name + .xlf
        default_out = str(Path(file_paths[0]).with_suffix('.xlf'))
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Converted XLIFF 2.2 File",
            default_out,
            "XLIFF Files (*.xlf *.xliff);;All Files (*)"
        )

        if not output_path:
            return

        try:
            # Convert using the module
            result = converter.convert_sdlxliff_to_xliff22(
                file_paths, 
                output_path, 
                verbose=False
            )
            
            # Ask if user wants to open the converted file
            reply = QMessageBox.question(
                self,
                "Conversion Successful",
                f"Converted {result['total_segments']} segments from {result['total_files']} file(s).\n\n"
                f"Open the converted file now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.open_xliff_file(str(output_path))
                
        except Exception as e:
            QMessageBox.critical(self, "Conversion Error", 
                               f"Failed to convert SDLXLIFF file(s):\n\n{str(e)}")

    def export_to_sdlxliff(self):
        """Export current XLIFF 2.2 back to SDLXLIFF file(s)"""
        if not self.xliff_file:
            QMessageBox.warning(self, "No File Open", 
                              "Please open an XLIFF 2.2 file first.")
            return
        
        try:
            # Import the merger module
            import xliff22_to_sdlxliff_batch_merger as merger
        except ImportError:
            QMessageBox.critical(self, "Module Missing", 
                               "The xliff22_to_sdlxliff_batch_merger.py module is not found.\n\n"
                               "Please ensure it's in the same directory as this editor.")
            return
        
        # Save current changes first
        if self.is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "Save changes to XLIFF 2.2 file before exporting?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Yes:
                self.save_xliff()
        
        # Select directory containing original SDLXLIFF files
        sdlxliff_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Directory with Original SDLXLIFF Files"
        )
        
        if not sdlxliff_dir:
            return
        
        # Select output directory for updated SDLXLIFF files
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory for Updated SDLXLIFF Files"
        )
        
        if not output_dir:
            return
        
        try:
            # Merge using the module
            results = merger.batch_merge_xliff22_to_sdlxliff(
                self.xliff_file,
                sdlxliff_dir,
                output_dir,
                dry_run=False
            )
            
            # Count results
            success_count = sum(1 for r in results if r['status'] == 'success')
            no_match_count = sum(1 for r in results if r['status'] == 'no_match')
            error_count = sum(1 for r in results if r['status'] == 'error')
            
            # Build message
            msg = f"Merge completed:\n\n"
            msg += f"✓ Successfully merged: {success_count} file(s)\n"
            if no_match_count > 0:
                msg += f"⚠ No match found: {no_match_count} file(s)\n"
            if error_count > 0:
                msg += f"✗ Errors: {error_count} file(s)\n"
            
            if success_count > 0:
                total_updated = sum(r.get('updated', 0) for r in results if r['status'] == 'success')
                msg += f"\nTotal segments updated: {total_updated}"
            
            if error_count > 0 or no_match_count > 0:
                QMessageBox.warning(self, "Merge Completed with Issues", msg)
            else:
                QMessageBox.information(self, "Merge Successful", msg)
                
        except Exception as e:
            QMessageBox.critical(self, "Merge Error", 
                               f"Failed to merge back to SDLXLIFF:\n\n{str(e)}")

    def import_from_mqxliff(self):
        """Import memoQ MQXLIFF file(s) and convert to XLIFF 2.2"""
        try:
            import mqxliff_xliff22_converter as converter
        except ImportError:
            QMessageBox.critical(self, "Module Missing",
                               "The mqxliff_xliff22_converter.py module is not found.\n\n"
                               "Please ensure it's in the same directory as this editor.")
            return

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select memoQ MQXLIFF File(s)",
            "",
            "memoQ XLIFF Files (*.mqxliff);;All Files (*)"
        )
        if not file_paths:
            return

        default_out = str(Path(file_paths[0]).with_suffix('.xlf'))
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Converted XLIFF 2.2 File",
            default_out,
            "XLIFF Files (*.xlf *.xliff);;All Files (*)"
        )
        if not output_path:
            return

        try:
            result = converter.convert_mqxliff_to_xliff22(
                file_paths, output_path, verbose=False
            )
            reply = QMessageBox.question(
                self,
                "Conversion Successful",
                f"Converted {result['total_segments']} segments from {result['total_files']} file(s).\n\n"
                f"Open the converted file now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.open_xliff_file(str(output_path))
        except Exception as e:
            QMessageBox.critical(self, "Conversion Error",
                               f"Failed to convert MQXLIFF file(s):\n\n{str(e)}")

    def export_to_mqxliff(self):
        """Export current XLIFF 2.2 translations back to memoQ MQXLIFF file(s)"""
        if not self.xliff_file:
            QMessageBox.warning(self, "No File Open",
                              "Please open an XLIFF 2.2 file first.")
            return

        try:
            import xliff22_to_mqxliff_merger as merger
        except ImportError:
            QMessageBox.critical(self, "Module Missing",
                               "The xliff22_to_mqxliff_merger.py module is not found.\n\n"
                               "Please ensure it's in the same directory as this editor.")
            return

        if self.is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "Save changes to XLIFF 2.2 file before exporting?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Yes:
                self.save_xliff()

        mqxliff_dir = QFileDialog.getExistingDirectory(
            self, "Select Directory with Original MQXLIFF Files"
        )
        if not mqxliff_dir:
            return

        output_dir = QFileDialog.getExistingDirectory(
            self, "Select Output Directory for Updated MQXLIFF Files"
        )
        if not output_dir:
            return

        try:
            results = merger.batch_merge_xliff22_to_mqxliff(
                self.xliff_file, mqxliff_dir, output_dir, dry_run=False
            )
            success_count = sum(1 for r in results if r['status'] == 'success')
            no_match_count = sum(1 for r in results if r['status'] == 'no_match')
            error_count = sum(1 for r in results if r['status'] == 'error')

            msg = "Merge completed:\n\n"
            msg += f"✓ Successfully merged: {success_count} file(s)\n"
            if no_match_count:
                msg += f"⚠ No match found: {no_match_count} file(s)\n"
            if error_count:
                msg += f"✗ Errors: {error_count} file(s)\n"
            if success_count:
                total_updated = sum(r.get('updated', 0) for r in results if r['status'] == 'success')
                msg += f"\nTotal segments updated: {total_updated}"

            if error_count or no_match_count:
                QMessageBox.warning(self, "Merge Completed with Issues", msg)
            else:
                QMessageBox.information(self, "Merge Successful", msg)
        except Exception as e:
            QMessageBox.critical(self, "Merge Error",
                               f"Failed to merge back to MQXLIFF:\n\n{str(e)}")

    def import_from_excel(self):
        """Import bilingual Excel file and convert to XLIFF 2.2"""
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            QMessageBox.critical(
                self, "Module Missing",
                "openpyxl is not installed.\n\nInstall it with:\n  pip install openpyxl"
            )
            return

        try:
            import excel_xliff22_converter as converter
            from excel_xliff22_converter import ExcelImportDialog
        except ImportError:
            QMessageBox.critical(
                self, "Module Missing",
                "excel_xliff22_converter.py is not found.\n\n"
                "Please ensure it's in the same directory as this editor."
            )
            return

        dialog = ExcelImportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        params = dialog.values()

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", "",
            "Excel Files (*.xlsx);;All Files (*)"
        )
        if not file_path:
            return

        default_out = str(Path(file_path).with_suffix('.xlf'))
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save Converted XLIFF 2.2 File", default_out,
            "XLIFF Files (*.xlf *.xliff);;All Files (*)"
        )
        if not output_path:
            return

        try:
            result = converter.convert_excel_to_xliff22(
                input_path=file_path,
                output_path=output_path,
                src_lang=params['src_lang'],
                tgt_lang=params['tgt_lang'],
                src_col=params['src_col'],
                tgt_col=params['tgt_col'],
                first_row=params['first_row'],
                segment=params['segment'],
            )
            reply = QMessageBox.question(
                self, "Conversion Successful",
                f"Converted {result['total_rows']} row(s) into "
                f"{result['total_units']} unit(s).\n\nOpen the converted file now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.open_xliff_file(str(output_path))
        except Exception as e:
            QMessageBox.critical(self, "Conversion Error",
                                 f"Failed to convert Excel file:\n\n{str(e)}")

    def export_to_excel(self):
        """Export current XLIFF 2.2 translations back to Excel in-place"""
        if not self.xliff_file:
            QMessageBox.warning(self, "No File Open",
                                "Please open an XLIFF 2.2 file first.")
            return

        file_tag = self.xliff_soup.find('file') if self.xliff_soup else None
        if not file_tag or not file_tag.get('x-excel-tgt-col'):
            QMessageBox.warning(
                self, "Not an Excel XLIFF",
                "This file was not imported from Excel.\n\n"
                "Only XLIFF files created via Excel import can be exported back."
            )
            return

        try:
            import openpyxl  # noqa: F401
        except ImportError:
            QMessageBox.critical(
                self, "Module Missing",
                "openpyxl is not installed.\n\nInstall it with:\n  pip install openpyxl"
            )
            return

        try:
            import xliff22_to_excel_merger as merger
        except ImportError:
            QMessageBox.critical(
                self, "Module Missing",
                "xliff22_to_excel_merger.py is not found.\n\n"
                "Please ensure it's in the same directory as this editor."
            )
            return

        if self.is_modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "Save changes to XLIFF 2.2 file before exporting?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Yes:
                self.save_xliff()
            else:
                confirm = QMessageBox.warning(
                    self, "Unsaved Changes Will Not Be Exported",
                    "Your unsaved edits will NOT be included in the export.\n\n"
                    "Only the last saved version will be written to Excel.\n\n"
                    "Continue anyway?",
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
                )
                if confirm != QMessageBox.StandardButton.Ok:
                    return

        default_name = file_tag.get('original', '')
        excel_path, _ = QFileDialog.getOpenFileName(
            self, "Select Target Excel File", default_name,
            "Excel Files (*.xlsx);;All Files (*)"
        )
        if not excel_path:
            return

        try:
            result = merger.merge_xliff22_to_excel(self.xliff_file, excel_path)
            QMessageBox.information(
                self, "Export Successful",
                f"Written {result['rows_written']} row(s) to "
                f"{Path(excel_path).name}."
            )
        except ValueError as e:
            QMessageBox.warning(self, "Export Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Export Error",
                                 f"Failed to write to Excel file:\n\n{str(e)}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    ex = XLIFFEditor()
    ex.show()
    ex.move_to_external_screen()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
