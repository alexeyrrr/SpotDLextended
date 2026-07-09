import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)

class RekordboxXMLExporter:
    def __init__(self, path_mapping=None):
        """
        Initializes the exporter.
        
        :param path_mapping: A dict of {source_prefix: replacement_prefix}
                             e.g., {"/mnt/d/": "D:/"}
        """
        self.path_mapping = path_mapping

    def to_windows_uri(self, path_str):
        """
        Converts a local file path to a Pioneer-compliant Windows URI.
        e.g., /mnt/d/Music/Track.mp3 -> file://localhost/D:/Music/Track.mp3
        """
        if not path_str:
            return ""

        # Normalize all slashes to forward slashes
        normalized_path = path_str.replace('\\', '/')

        # Apply prefix mapping if provided
        mapped = False
        if self.path_mapping:
            for src, dest in self.path_mapping.items():
                if normalized_path.startswith(src):
                    normalized_path = dest + normalized_path[len(src):]
                    mapped = True
                    break

        # Automatically translate WSL path /mnt/c/ to C:/ if no mapping was applied
        if not mapped:
            match = re.match(r'^/mnt/([a-zA-Z])/(.*)', normalized_path)
            if match:
                drive_letter = match.group(1).upper()
                rest = match.group(2)
                normalized_path = f"{drive_letter}:/{rest}"

        # Standard URL-encode path segments while leaving ':' and '/' intact
        encoded_path = urllib.parse.quote(normalized_path, safe="/:")

        # Construct final URI
        if re.match(r'^[a-zA-Z]:/', encoded_path):
            return f"file://localhost/{encoded_path}"
        elif encoded_path.startswith("/"):
            return f"file://localhost{encoded_path}"
        else:
            return f"file://localhost/{encoded_path}"

    def get_file_kind(self, path_str):
        """
        Returns Rekordbox 'Kind' string based on file extension.
        """
        ext = os.path.splitext(path_str)[1].lower()
        if ext == ".mp3":
            return "MP3 File"
        elif ext == ".flac":
            return "FLAC File"
        elif ext == ".wav":
            return "WAV File"
        elif ext == ".m4a":
            return "M4A File"
        elif ext == ".aac":
            return "AAC File"
        elif ext == ".aif" or ext == ".aiff":
            return "AIFF File"
        else:
            return "Audio File"

    def export(self, tracks, playlist_name, output_xml_path):
        """
        Exports list of tracks to the specified Rekordbox XML file.
        Uses a Read-Merge-Write approach if the XML already exists.
        
        :param tracks: A list of dicts/objects containing:
                       title, artist, album, absolute_path, bpm, key, isrc, duration
        :param playlist_name: The target playlist name
        :param output_xml_path: Where to save the XML file
        """
        # 1. Read existing XML or initialize a new one
        tree = None
        root = None
        collection = None
        playlists = None
        
        if os.path.exists(output_xml_path):
            try:
                tree = ET.parse(output_xml_path)
                root = tree.getroot()
                if root.tag != 'DJ_PLAYLISTS':
                    logger.warning("Existing XML does not have 'DJ_PLAYLISTS' root. Creating new XML.")
                    tree = None
            except Exception as e:
                logger.warning(f"Failed to parse existing XML at {output_xml_path}: {e}. Re-creating.")
                tree = None

        if tree is None:
            # Setup base structure
            root = ET.Element('DJ_PLAYLISTS', Version='1.0.0')
            ET.SubElement(root, 'PRODUCT', Name='rekordbox', Version='7.0.0', Company='AlphaTheta')
            collection = ET.SubElement(root, 'COLLECTION', Entries='0')
            playlists = ET.SubElement(root, 'PLAYLISTS')
            ET.SubElement(playlists, 'NODE', Type='0', Name='ROOT')
            tree = ET.ElementTree(root)
        else:
            # Find collection
            collection = root.find('COLLECTION')
            if collection is None:
                collection = ET.SubElement(root, 'COLLECTION', Entries='0')
            # Find playlists
            playlists = root.find('PLAYLISTS')
            if playlists is None:
                playlists = ET.SubElement(root, 'PLAYLISTS')

        # Find ROOT folder in playlists
        root_node = None
        for node in playlists.findall('NODE'):
            if node.get('Type') == '0' and node.get('Name') == 'ROOT':
                root_node = node
                break
        if root_node is None:
            root_node = ET.SubElement(playlists, 'NODE', Type='0', Name='ROOT')

        # 2. Extract existing tracks from COLLECTION
        location_to_id = {}
        max_id = 0
        
        for track_node in collection.findall('TRACK'):
            track_id_str = track_node.get('TrackID')
            location = track_node.get('Location')
            if track_id_str and location:
                location_to_id[location] = track_id_str
                try:
                    tid_val = int(track_id_str)
                    if tid_val > max_id:
                        max_id = tid_val
                except ValueError:
                    pass

        # 3. Process new tracks and add to COLLECTION if not present
        playlist_track_ids = []
        
        for track_data in tracks:
            # Handle objects or dicts gracefully
            if hasattr(track_data, 'get'):
                title = track_data.get('title', '')
                artist = track_data.get('artist', '')
                album = track_data.get('album', '')
                bpm = track_data.get('bpm', '')
                key = track_data.get('key', '')
                isrc = track_data.get('isrc', '')
                abs_path = track_data.get('absolute_path', '')
                duration = track_data.get('duration', None)
            else:
                title = getattr(track_data, 'title', '')
                artist = getattr(track_data, 'artist', '')
                album = getattr(track_data, 'album', '')
                bpm = getattr(track_data, 'bpm', '')
                key = getattr(track_data, 'key', '')
                isrc = getattr(track_data, 'isrc', '')
                abs_path = getattr(track_data, 'absolute_path', '')
                duration = getattr(track_data, 'duration', None)

            if not abs_path:
                logger.warning(f"Track '{title}' has no absolute path. Skipping from Rekordbox XML.")
                continue

            windows_uri = self.to_windows_uri(abs_path)

            # Check if track already in collection
            if windows_uri in location_to_id:
                track_id = location_to_id[windows_uri]
            else:
                # Assign new sequential TrackID
                max_id += 1
                track_id = str(max_id)
                location_to_id[windows_uri] = track_id
                
                # Build new TRACK element attributes
                kind = self.get_file_kind(abs_path)
                
                track_attrs = {
                    'TrackID': track_id,
                    'Name': title,
                    'Artist': artist,
                    'Composer': '',
                    'Album': album if album else '',
                    'Grouping': '',
                    'Genre': '',
                    'Kind': kind,
                    'Comments': '',
                    'Location': windows_uri
                }

                # Add optional fields if populated
                if isrc:
                    track_attrs['ISRC'] = isrc
                if key:
                    track_attrs['Tonality'] = key
                
                if bpm:
                    try:
                        # Clean up / format BPM as a float with 2 decimal places
                        clean_bpm = float(str(bpm).replace(',', '.').strip())
                        track_attrs['AverageBpm'] = f"{clean_bpm:.2f}"
                    except ValueError:
                        # Fallback to string if not float-convertible
                        track_attrs['AverageBpm'] = str(bpm)

                if duration is not None:
                    try:
                        track_attrs['TotalTime'] = str(int(duration))
                    except (ValueError, TypeError):
                        pass

                # Create TRACK node
                ET.SubElement(collection, 'TRACK', **track_attrs)

            playlist_track_ids.append(track_id)

        # Update COLLECTION Entries count
        total_tracks = len(collection.findall('TRACK'))
        collection.set('Entries', str(total_tracks))

        # 4. Create or update target playlist
        target_playlist = None
        for node in root_node.findall('NODE'):
            if node.get('Type') == '1' and node.get('Name') == playlist_name:
                target_playlist = node
                break

        if target_playlist is None:
            target_playlist = ET.SubElement(root_node, 'NODE', Type='1', Name=playlist_name, Entries='0')
        
        # Clear existing children from target playlist node using list slicing
        target_playlist[:] = []
        
        # Map current tracks to the playlist
        for tid in playlist_track_ids:
            ET.SubElement(target_playlist, 'TRACKKey', Key=tid)

        target_playlist.set('Entries', str(len(playlist_track_ids)))

        # 5. Pretty-print and save XML
        try:
            # Use built-in ElementTree indentation (Python 3.9+)
            ET.indent(root, space="  ", level=0)
        except AttributeError:
            pass # Fallback if ElementTree doesn't support indent

        # Ensure directory exists and write
        os.makedirs(os.path.dirname(os.path.abspath(output_xml_path)), exist_ok=True)
        
        tree.write(output_xml_path, encoding='utf-8', xml_declaration=True)
        logger.info(f"  [✓] Rekordbox XML updated: {output_xml_path} (Collection: {total_tracks} tracks, Playlist '{playlist_name}': {len(playlist_track_ids)} tracks)")
