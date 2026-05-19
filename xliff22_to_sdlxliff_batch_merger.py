#!/usr/bin/env python3
"""
XLIFF 2.2 to SDLXLIFF Batch Merger
Automatically processes multiple <file> elements in XLIFF 2.2 and merges them
back into their corresponding SDLXLIFF files based on file ID matching.
"""

import argparse
import sys
from pathlib import Path
from lxml import etree

# Namespace definitions
NS_XLIFF12 = {
    'xliff12': 'urn:oasis:names:tc:xliff:document:1.2',
    'sdl': 'http://sdl.com/FileTypes/SdlXliff/1.0'
}

NS_XLIFF22 = {
    'xliff22': 'urn:oasis:names:tc:xliff:document:2.0',
    'xml': 'http://www.w3.org/XML/1998/namespace'
}


def map_xliff22_state_to_sdl(state):
    """Map XLIFF 2.2 state values back to SDL Trados status values."""
    if not state:
        return 'Draft'
    
    state_mapping = {
        'initial': 'Draft',
        'translated': 'Translated',
        'reviewed': 'ApprovedTranslation',
        'final': 'ApprovedSignOff',
        'needs-review-translation': 'RejectedTranslation',
        'needs-review-adaptation': 'RejectedTranslation',
        'needs-review-l10n': 'RejectedTranslation',
    }
    
    return state_mapping.get(state, 'Translated')


def extract_text_from_xliff22(element):
    """
    Extract text content from XLIFF 2.2 element, converting inline tags back to XLIFF 1.2 format.
    """
    result = []
    
    if element.text:
        result.append(element.text)
    
    for child in element:
        tag = etree.QName(child).localname
        
        if tag == 'pc':
            # Convert <pc> back to <g>
            g_elem = etree.Element('{urn:oasis:names:tc:xliff:document:1.2}g')
            if 'id' in child.attrib:
                g_elem.set('id', child.get('id'))
            
            # Recursively extract content
            inner_content = extract_text_from_xliff22(child)
            if inner_content:
                if isinstance(inner_content[0], str):
                    g_elem.text = inner_content[0]
                    inner_content = inner_content[1:]
                for item in inner_content:
                    if isinstance(item, str):
                        if len(g_elem):
                            g_elem[-1].tail = (g_elem[-1].tail or '') + item
                        else:
                            g_elem.text = (g_elem.text or '') + item
                    else:
                        g_elem.append(item)
            
            result.append(g_elem)
            
        elif tag == 'ph':
            # Convert <ph> back to <x>
            x_elem = etree.Element('{urn:oasis:names:tc:xliff:document:1.2}x')
            if 'id' in child.attrib:
                x_elem.set('id', child.get('id'))
            if child.text:
                x_elem.text = child.text
            result.append(x_elem)
        else:
            # Preserve other elements
            new_elem = etree.Element(child.tag)
            new_elem.attrib.update(child.attrib)
            
            inner_content = extract_text_from_xliff22(child)
            if inner_content:
                if isinstance(inner_content[0], str):
                    new_elem.text = inner_content[0]
                    inner_content = inner_content[1:]
                for item in inner_content:
                    if isinstance(item, str):
                        if len(new_elem):
                            new_elem[-1].tail = (new_elem[-1].tail or '') + item
                        else:
                            new_elem.text = (new_elem.text or '') + item
                    else:
                        new_elem.append(item)
            
            result.append(new_elem)
        
        if child.tail:
            result.append(child.tail)
    
    return result


def build_segment_map_from_file_element(file_elem):
    """
    Build a mapping of segment IDs to their translation data from a single file element.
    
    Returns:
        dict: Mapping of {unit_id: {segment_position: {target, state}}}
    """
    segment_map = {}
    
    for unit in file_elem.findall('{%s}unit' % NS_XLIFF22['xliff22'], NS_XLIFF22):
        unit_id = unit.get('id')
        
        if unit_id not in segment_map:
            segment_map[unit_id] = {}
        
        # Process segments within this unit
        segment_counter = 0
        for segment in unit.findall('{%s}segment' % NS_XLIFF22['xliff22'], NS_XLIFF22):
            segment_counter += 1
            state = segment.get('state')
            
            # Get target content
            target_elem = segment.find('{%s}target' % NS_XLIFF22['xliff22'], NS_XLIFF22)
            
            if target_elem is not None:
                # Extract target content with tags
                target_content = extract_text_from_xliff22(target_elem)
                
                # Store in map using segment position
                segment_map[unit_id][segment_counter] = {
                    'target_content': target_content,
                    'state': state
                }
    
    return segment_map


def update_sdlxliff_targets(sdlxliff_path, segment_map, output_path):
    """
    Update the SDLXLIFF file with translations from the segment map.
    """
    # Parse SDLXLIFF
    tree = etree.parse(sdlxliff_path)
    root = tree.getroot()
    
    updated_count = 0
    skipped_count = 0
    
    # Process each trans-unit
    for trans_unit in root.findall('.//xliff12:trans-unit', NS_XLIFF12):
        unit_id = trans_unit.get('id')
        
        # Skip if no translations for this unit
        if unit_id not in segment_map:
            continue
        
        # Get target element (create if doesn't exist)
        target = trans_unit.find('xliff12:target', NS_XLIFF12)
        if target is None:
            # Create target element after source
            source = trans_unit.find('xliff12:source', NS_XLIFF12)
            target_index = list(trans_unit).index(source) + 1
            target = etree.Element('{urn:oasis:names:tc:xliff:document:1.2}target')
            trans_unit.insert(target_index, target)
        
        # Get seg-defs for status updates
        seg_defs = trans_unit.find('sdl:seg-defs', NS_XLIFF12)
        
        # Find all target mrk segments
        target_mrks = target.findall('.//xliff12:mrk[@mtype="seg"]', NS_XLIFF12)
        
        if target_mrks:
            # Update each segment
            segment_counter = 0
            for mrk in target_mrks:
                segment_counter += 1
                mid = mrk.get('mid')
                
                # Check if we have translation for this segment
                if segment_counter in segment_map[unit_id]:
                    translation_data = segment_map[unit_id][segment_counter]
                    
                    # Clear existing content in mrk
                    mrk.clear()
                    mrk.set('mtype', 'seg')
                    if mid:
                        mrk.set('mid', mid)
                    
                    # Add new translation content
                    target_content = translation_data['target_content']
                    if target_content:
                        if isinstance(target_content[0], str):
                            mrk.text = target_content[0]
                            target_content = target_content[1:]
                        
                        for item in target_content:
                            if isinstance(item, str):
                                if len(mrk):
                                    mrk[-1].tail = (mrk[-1].tail or '') + item
                                else:
                                    mrk.text = (mrk.text or '') + item
                            else:
                                mrk.append(item)
                    
                    # Update status in seg-defs if available
                    if seg_defs is not None and mid:
                        seg_def = seg_defs.find(f'sdl:seg[@id="{mid}"]', NS_XLIFF12)
                        if seg_def is not None:
                            new_status = map_xliff22_state_to_sdl(translation_data['state'])
                            seg_def.set('conf', new_status)
                    
                    updated_count += 1
                else:
                    skipped_count += 1
        else:
            # No segmented structure, update simple target
            if 1 in segment_map[unit_id]:
                translation_data = segment_map[unit_id][1]
                
                # Clear and rebuild target
                target.clear()
                target_content = translation_data['target_content']
                
                if target_content:
                    if isinstance(target_content[0], str):
                        target.text = target_content[0]
                        target_content = target_content[1:]
                    
                    for item in target_content:
                        if isinstance(item, str):
                            if len(target):
                                target[-1].tail = (target[-1].tail or '') + item
                            else:
                                target.text = (target.text or '') + item
                        else:
                            target.append(item)
                
                updated_count += 1
            else:
                skipped_count += 1
    
    # Write output WITHOUT pretty printing
    tree.write(output_path, encoding='utf-8', xml_declaration=True, pretty_print=False)
    
    return updated_count, skipped_count


def find_sdlxliff_for_file_id(file_id, sdlxliff_dir):
    """
    Find the SDLXLIFF file that corresponds to the file_id.
    Now handles full filenames with .sdlxliff extension.
    
    Strategies:
    1. Direct match: if file_id ends with .sdlxliff, look for exact filename
    2. Add .sdlxliff extension if not present
    3. Remove language suffix and add .sdlxliff
    4. Case-insensitive matching
    """
    sdlxliff_dir = Path(sdlxliff_dir)
    
    # Strategy 1: Direct match if file_id ends with .sdlxliff
    if file_id.endswith('.sdlxliff'):
        direct_match = sdlxliff_dir / file_id
        if direct_match.exists():
            return direct_match
    
    # Strategy 2: Add .sdlxliff if not present
    if not file_id.endswith('.sdlxliff'):
        with_ext = sdlxliff_dir / f"{file_id}.sdlxliff"
        if with_ext.exists():
            return with_ext
    
    # Strategy 3: Remove language suffix and try
    # Common patterns: _pl, _de, _fr, etc.
    if '_' in file_id:
        # Remove extension if present
        base_id = file_id.replace('.sdlxliff', '')
        base_name = '_'.join(base_id.split('_')[:-1])
        base_match = sdlxliff_dir / f"{base_name}.sdlxliff"
        if base_match.exists():
            return base_match
    
    # Strategy 4: Case-insensitive search
    file_id_lower = file_id.lower()
    for sdlxliff_file in sdlxliff_dir.glob("*.sdlxliff"):
        if sdlxliff_file.name.lower() == file_id_lower:
            return sdlxliff_file
        # Also try without extension
        if file_id.endswith('.sdlxliff'):
            base_id = file_id.replace('.sdlxliff', '')
            if sdlxliff_file.stem.lower() == base_id.lower():
                return sdlxliff_file
    
    return None


def batch_merge_xliff22_to_sdlxliff(xliff22_path, sdlxliff_dir, output_dir, dry_run=False):
    """
    Process all file elements in XLIFF 2.2 and merge back to corresponding SDLXLIFF files.
    
    Args:
        xliff22_path: Path to XLIFF 2.2 file with multiple <file> elements
        sdlxliff_dir: Directory containing original SDLXLIFF files
        output_dir: Directory to write updated SDLXLIFF files
        dry_run: If True, only show what would be processed without writing files
    """
    # Parse XLIFF 2.2
    tree = etree.parse(xliff22_path)
    root = tree.getroot()
    
    # Find all file elements
    file_elements = root.findall('.//{%s}file' % NS_XLIFF22['xliff22'], NS_XLIFF22)
    
    print(f"Found {len(file_elements)} file element(s) in XLIFF 2.2")
    print("=" * 70)
    
    # Ensure output directory exists
    output_dir = Path(output_dir)
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    
    for idx, file_elem in enumerate(file_elements, 1):
        file_id = file_elem.get('id')
        
        print(f"\n[{idx}/{len(file_elements)}] Processing file ID: {file_id}")
        print("-" * 70)
        
        # Find corresponding SDLXLIFF file
        sdlxliff_path = find_sdlxliff_for_file_id(file_id, sdlxliff_dir)
        
        if sdlxliff_path is None:
            print(f"  ✗ No matching SDLXLIFF file found")
            print(f"    Tried: {file_id}")
            if not file_id.endswith('.sdlxliff'):
                print(f"    Tried: {file_id}.sdlxliff")
            if '_' in file_id:
                base_name = file_id.replace('.sdlxliff', '')
                base_name = '_'.join(base_name.split('_')[:-1])
                print(f"    Tried: {base_name}.sdlxliff")
            results.append({
                'file_id': file_id,
                'status': 'no_match',
                'sdlxliff': None
            })
            continue
        
        print(f"  ✓ Matched to: {sdlxliff_path.name}")
        
        # Build segment map from this file element
        segment_map = build_segment_map_from_file_element(file_elem)
        total_units = len(segment_map)
        total_segments = sum(len(segments) for segments in segment_map.values())
        
        print(f"  Segments to merge: {total_segments} in {total_units} units")
        
        if dry_run:
            print(f"  [DRY RUN] Would write to: {output_dir / sdlxliff_path.name}")
            results.append({
                'file_id': file_id,
                'status': 'dry_run',
                'sdlxliff': str(sdlxliff_path),
                'segments': total_segments
            })
            continue
        
        # Update SDLXLIFF
        output_path = output_dir / sdlxliff_path.name
        try:
            updated, skipped = update_sdlxliff_targets(sdlxliff_path, segment_map, output_path)
            print(f"  ✓ Updated {updated} segments")
            if skipped > 0:
                print(f"  ⚠ Skipped {skipped} segments (no translation)")
            print(f"  ✓ Written to: {output_path}")
            
            results.append({
                'file_id': file_id,
                'status': 'success',
                'sdlxliff': str(sdlxliff_path),
                'output': str(output_path),
                'updated': updated,
                'skipped': skipped
            })
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({
                'file_id': file_id,
                'status': 'error',
                'sdlxliff': str(sdlxliff_path),
                'error': str(e)
            })
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Batch merge XLIFF 2.2 translations back into multiple SDLXLIFF files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script processes XLIFF 2.2 files containing multiple <file> elements and
automatically merges translations back into the corresponding SDLXLIFF files.

File Matching Logic:
  The script matches file IDs to SDLXLIFF files using these strategies:
  1. Direct match if file_id includes .sdlxliff extension
  2. Add .sdlxliff extension if not present
  3. Remove language suffix: file_id_pl.sdlxliff → file_id.sdlxliff
  4. Case-insensitive matching

Examples:
  # Basic usage
  %(prog)s merged.xlf --sdlxliff-dir ./originals --output-dir ./updated
  
  # Dry run to see what would be processed
  %(prog)s merged.xlf --sdlxliff-dir ./originals --output-dir ./updated --dry-run
  
  # Same input and output directory (overwrites originals - use with caution!)
  %(prog)s merged.xlf --sdlxliff-dir ./files --output-dir ./files
        """
    )
    
    parser.add_argument('xliff22', help='XLIFF 2.2 file with multiple <file> elements')
    parser.add_argument('--sdlxliff-dir', required=True,
                        help='Directory containing original SDLXLIFF files')
    parser.add_argument('--output-dir', required=True,
                        help='Directory to write updated SDLXLIFF files')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed without writing files')
    
    args = parser.parse_args()
    
    # Validate paths
    xliff22_path = Path(args.xliff22)
    if not xliff22_path.exists():
        print(f"Error: XLIFF 2.2 file not found: {xliff22_path}", file=sys.stderr)
        sys.exit(1)
    
    sdlxliff_dir = Path(args.sdlxliff_dir)
    if not sdlxliff_dir.exists():
        print(f"Error: SDLXLIFF directory not found: {sdlxliff_dir}", file=sys.stderr)
        sys.exit(1)
    
    print("=" * 70)
    print("XLIFF 2.2 → SDLXLIFF Batch Merger")
    print("=" * 70)
    print(f"XLIFF 2.2 file: {xliff22_path.name}")
    print(f"SDLXLIFF directory: {sdlxliff_dir}")
    print(f"Output directory: {args.output_dir}")
    if args.dry_run:
        print("Mode: DRY RUN (no files will be written)")
    print()
    
    try:
        results = batch_merge_xliff22_to_sdlxliff(
            xliff22_path,
            sdlxliff_dir,
            args.output_dir,
            args.dry_run
        )
        
        # Print summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        
        success_count = sum(1 for r in results if r['status'] == 'success')
        no_match_count = sum(1 for r in results if r['status'] == 'no_match')
        error_count = sum(1 for r in results if r['status'] == 'error')
        dry_run_count = sum(1 for r in results if r['status'] == 'dry_run')
        
        if dry_run_count > 0:
            print(f"✓ Would process {dry_run_count} file(s)")
        if success_count > 0:
            print(f"✓ Successfully merged {success_count} file(s)")
            total_updated = sum(r.get('updated', 0) for r in results if r['status'] == 'success')
            print(f"✓ Total segments updated: {total_updated}")
        if no_match_count > 0:
            print(f"⚠ No match found for {no_match_count} file(s)")
        if error_count > 0:
            print(f"✗ Errors in {error_count} file(s)")
        
        if not args.dry_run and success_count > 0:
            print(f"\n✓ Updated files written to: {args.output_dir}")
        
        # Exit with error if any files failed
        if error_count > 0 or no_match_count > 0:
            sys.exit(1)
            
    except Exception as e:
        print(f"\n✗ Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
