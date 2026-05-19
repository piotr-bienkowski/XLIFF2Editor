"""
SDLXLIFF to XLIFF 2.2 Converter Module
Can be used as a standalone script or imported as a module
"""

import sys
from pathlib import Path
from lxml import etree

# Namespace definitions
NS = {
    'xliff12': 'urn:oasis:names:tc:xliff:document:1.2',
    'sdl': 'http://sdl.com/FileTypes/SdlXliff/1.0'
}

# XLIFF 2.2 namespace
NS_XLIFF22 = 'urn:oasis:names:tc:xliff:document:2.0'
NS_XML = 'http://www.w3.org/XML/1998/namespace'


def extract_text_and_tags(element, ns_xliff22=NS_XLIFF22):
    """
    Extract text and preserve inline tags from an element.
    Removes mrk wrappers but keeps inline formatting tags, converting them to XLIFF 2.2 format.
    """
    result = []
    
    if element.text:
        result.append(element.text)
    
    for child in element:
        tag = etree.QName(child).localname
        
        if tag == 'mrk':
            child_content = extract_text_and_tags(child, ns_xliff22)
            result.extend(child_content)
        elif tag in ['g', 'bpt', 'ept']:
            pc_elem = etree.Element('{%s}pc' % ns_xliff22)
            if 'id' in child.attrib:
                pc_elem.set('id', child.get('id'))
            
            inner_content = extract_text_and_tags(child, ns_xliff22)
            if inner_content:
                if isinstance(inner_content[0], str):
                    pc_elem.text = inner_content[0]
                    inner_content = inner_content[1:]
                for item in inner_content:
                    if isinstance(item, str):
                        if len(pc_elem):
                            pc_elem[-1].tail = (pc_elem[-1].tail or '') + item
                        else:
                            pc_elem.text = (pc_elem.text or '') + item
                    else:
                        pc_elem.append(item)
            
            result.append(pc_elem)
        elif tag == 'x':
            ph_elem = etree.Element('{%s}ph' % ns_xliff22)
            if 'id' in child.attrib:
                ph_elem.set('id', child.get('id'))
            if child.text:
                ph_elem.text = child.text
            result.append(ph_elem)
        elif tag == 'ph':
            ph_elem = etree.Element('{%s}ph' % ns_xliff22)
            if 'id' in child.attrib:
                ph_elem.set('id', child.get('id'))
            if child.text:
                ph_elem.text = child.text
            result.append(ph_elem)
        else:
            new_elem = etree.Element(child.tag)
            new_elem.attrib.update(child.attrib)
            
            inner_content = extract_text_and_tags(child, ns_xliff22)
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


def map_status(sdl_status):
    """Map SDL Trados status values to XLIFF 2.2 state values."""
    if not sdl_status:
        return None
    
    status_mapping = {
        'Draft': 'initial',
        'Translated': 'translated',
        'ApprovedTranslation': 'translated',
        'ApprovedSignOff': 'final',
        'RejectedTranslation': 'needs-review-translation',
        'RejectedSignOff': 'needs-review-translation',
    }
    
    return status_mapping.get(sdl_status, sdl_status.lower())


def process_sdlxliff_file(input_path, file_id, segment_counter=0):
    """
    Process a single SDLXLIFF file and return the file element with all units.
    
    Returns:
        tuple: (file_element, new_segment_counter, source_lang, target_lang)
    """
    tree = etree.parse(input_path)
    root = tree.getroot()
    
    file_elem = root.find('.//xliff12:file', NS)
    source_lang = file_elem.get('source-language', 'en') if file_elem is not None else 'en'
    target_lang = file_elem.get('target-language', '') if file_elem is not None else ''
    
    file22 = etree.Element('{%s}file' % NS_XLIFF22, id=file_id)
    
    for trans_unit in root.findall('.//xliff12:trans-unit', NS):
        if trans_unit.get('translate') == 'no':
            continue
        
        unit_id = trans_unit.get('id', f'unit_{segment_counter}')
        
        source_elem = trans_unit.find('xliff12:source', NS)
        if source_elem is not None:
            source_text = ''.join(source_elem.itertext()).strip()
            if not source_text:
                continue
        
        seg_source = trans_unit.find('xliff12:seg-source', NS)
        target = trans_unit.find('xliff12:target', NS)
        
        seg_defs = trans_unit.find('sdl:seg-defs', NS)
        status_map = {}
        locked_map = {}
        if seg_defs is not None:
            for seg_def in seg_defs.findall('sdl:seg', NS):
                seg_id = seg_def.get('id')
                conf = seg_def.get('conf')
                locked = seg_def.get('locked')
                if seg_id and conf:
                    status_map[seg_id] = map_status(conf)
                if seg_id and locked:
                    locked_map[seg_id] = (locked.lower() == 'true')
        
        unit22 = etree.SubElement(file22, '{%s}unit' % NS_XLIFF22, id=unit_id)
        
        if seg_source is not None:
            source_mrks = seg_source.findall('.//xliff12:mrk[@mtype="seg"]', NS)
            
            target_mrks = {}
            if target is not None:
                for mrk in target.findall('.//xliff12:mrk[@mtype="seg"]', NS):
                    mid = mrk.get('mid')
                    if mid:
                        target_mrks[mid] = mrk
            
            for mrk in source_mrks:
                mid = mrk.get('mid')
                
                mrk_text = ''.join(mrk.itertext()).strip()
                if not mrk_text:
                    continue
                
                segment_counter += 1
                
                segment_attrs = {'id': str(segment_counter)}
                if mid in status_map:
                    segment_attrs['state'] = status_map[mid]
                
                if mid in locked_map and locked_map[mid]:
                    segment_attrs['translate'] = 'no'
                
                segment22 = etree.SubElement(unit22, '{%s}segment' % NS_XLIFF22, **segment_attrs)
                
                source22 = etree.SubElement(segment22, '{%s}source' % NS_XLIFF22)
                source22.set('{%s}space' % NS_XML, 'preserve')
                
                content = extract_text_and_tags(mrk)
                if content:
                    if isinstance(content[0], str):
                        source22.text = content[0]
                        content = content[1:]
                    
                    for item in content:
                        if isinstance(item, str):
                            if len(source22):
                                source22[-1].tail = (source22[-1].tail or '') + item
                            else:
                                source22.text = (source22.text or '') + item
                        else:
                            source22.append(item)
                
                if mid in target_mrks:
                    target_mrk = target_mrks[mid]
                    target22 = etree.SubElement(segment22, '{%s}target' % NS_XLIFF22)
                    target22.set('{%s}space' % NS_XML, 'preserve')
                    
                    content = extract_text_and_tags(target_mrk)
                    if content:
                        if isinstance(content[0], str):
                            target22.text = content[0]
                            content = content[1:]
                        
                        for item in content:
                            if isinstance(item, str):
                                if len(target22):
                                    target22[-1].tail = (target22[-1].tail or '') + item
                                else:
                                    target22.text = (target22.text or '') + item
                            else:
                                target22.append(item)
        else:
            if source_elem is None:
                continue
            
            source_text = ''.join(source_elem.itertext()).strip()
            if not source_text:
                continue
            
            segment_counter += 1
            segment22 = etree.SubElement(unit22, '{%s}segment' % NS_XLIFF22, id=str(segment_counter))
            
            source22 = etree.SubElement(segment22, '{%s}source' % NS_XLIFF22)
            source22.set('{%s}space' % NS_XML, 'preserve')
            source22.text = source_text
            
            if target is not None:
                target_text = ''.join(target.itertext()).strip()
                if target_text:
                    target22 = etree.SubElement(segment22, '{%s}target' % NS_XLIFF22)
                    target22.set('{%s}space' % NS_XML, 'preserve')
                    target22.text = target_text
        
        if not len(unit22):
            file22.remove(unit22)
    
    return file22, segment_counter, source_lang, target_lang


def convert_sdlxliff_to_xliff22(input_paths, output_path, verbose=True):
    """
    Convert one or more SDLXLIFF files to a single XLIFF 2.2 file.
    
    Args:
        input_paths: List of Path objects or strings pointing to SDLXLIFF files
        output_path: Path object or string for output XLIFF 2.2 file
        verbose: If True, print progress messages
        
    Returns:
        dict: Statistics about the conversion (total_segments, total_files, etc.)
    """
    if not input_paths:
        raise ValueError("No input files provided")
    
    # Convert to Path objects if needed
    input_paths = [Path(p) for p in input_paths]
    output_path = Path(output_path)
    
    # Determine languages from first file
    first_tree = etree.parse(input_paths[0])
    first_root = first_tree.getroot()
    first_file = first_root.find('.//xliff12:file', NS)
    
    source_lang = first_file.get('source-language', 'en') if first_file is not None else 'en'
    target_lang = first_file.get('target-language', '') if first_file is not None else ''
    
    # Create XLIFF 2.2 root
    xliff22_root = etree.Element(
        '{%s}xliff' % NS_XLIFF22,
        version='2.2',
        srcLang=source_lang,
        nsmap={
            None: NS_XLIFF22,
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'xml': NS_XML
        }
    )
    
    if target_lang:
        xliff22_root.set('trgLang', target_lang)
    
    xliff22_root.set(
        '{http://www.w3.org/2001/XMLSchema-instance}schemaLocation',
        'urn:oasis:names:tc:xliff:document:2.0 '
        'https://docs.oasis-open.org/xliff/xliff-core/v2.1/os/schemas/xliff_core_2.0.xsd'
    )
    
    segment_counter = 0
    total_segments = 0
    processed_files = []
    
    for idx, input_path in enumerate(input_paths, start=1):
        if verbose:
            print(f"Processing {idx}/{len(input_paths)}: {input_path.name}")
        
        # Use full filename including .sdlxliff extension as file_id
        file_id = input_path.name
        
        file22, segment_counter, src_lang, trg_lang = process_sdlxliff_file(
            input_path, file_id, segment_counter
        )
        
        units = file22.findall('{%s}unit' % NS_XLIFF22)
        if units:
            xliff22_root.append(file22)
            segments_in_file = len(file22.findall('.//{%s}segment' % NS_XLIFF22))
            total_segments += segments_in_file
            processed_files.append({
                'filename': input_path.name,
                'units': len(units),
                'segments': segments_in_file
            })
            if verbose:
                print(f"  ✓ Added {len(units)} units with {segments_in_file} segments")
        else:
            if verbose:
                print(f"  ⚠ Skipped (no valid segments)")
    
    # Write output WITHOUT pretty printing
    output_tree = etree.ElementTree(xliff22_root)
    output_tree.write(
        output_path,
        encoding='utf-8',
        xml_declaration=True,
        pretty_print=False
    )
    
    if verbose:
        print(f"\n✓ Converted {total_segments} total segments from {len(input_paths)} file(s)")
        print(f"✓ Output written to: {output_path}")
    
    return {
        'total_segments': total_segments,
        'total_files': len(processed_files),
        'files': processed_files,
        'output_path': str(output_path)
    }


def main():
    """Command-line interface for the converter"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Convert SDLXLIFF to XLIFF 2.2 (supports multiple input files)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file
  %(prog)s input.sdlxliff -o output.xlf
  
  # Multiple files (merged into one XLIFF 2.2 with multiple <file> elements)
  %(prog)s file1.sdlxliff file2.sdlxliff file3.sdlxliff -o merged.xlf
  
  # Using wildcards
  %(prog)s *.sdlxliff -o all_files.xlf
        """
    )
    
    parser.add_argument('input', nargs='+', help='Input SDLXLIFF file(s)')
    parser.add_argument('-o', '--output', required=True, help='Output XLIFF 2.2 file')
    parser.add_argument('-q', '--quiet', action='store_true', help='Suppress progress messages')
    
    args = parser.parse_args()
    
    # Validate input files
    input_paths = []
    for pattern in args.input:
        path = Path(pattern)
        if path.exists():
            input_paths.append(path)
        else:
            print(f"Warning: File not found: {pattern}", file=sys.stderr)
    
    if not input_paths:
        print("Error: No valid input files found", file=sys.stderr)
        sys.exit(1)
    
    output_path = Path(args.output)
    
    if not args.quiet:
        print(f"Converting {len(input_paths)} SDLXLIFF file(s) to XLIFF 2.2")
        print(f"Output: {output_path.name}\n")
    
    try:
        result = convert_sdlxliff_to_xliff22(input_paths, output_path, verbose=not args.quiet)
        if not args.quiet:
            print("\n✓ Conversion completed successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error during conversion: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
