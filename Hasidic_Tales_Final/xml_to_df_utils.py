from lxml import etree
from typing import Union, List, Dict

import re
import os
from pathlib import Path
PathLike = Union[os.PathLike, Path]


# Function to parse the TEI XML file and extract all <div> elements of type "story" with their xml:id
def extract_story_divs(file_path, XML_NAMESPACE, NAMESPACES):
    # Parse the XML file
    tree = etree.parse(file_path)
    
    # Find all <div> elements with type="story" and xml:id attributes
    story_divs = []
    
    # XPath query to find all <div> elements with type="story" and xml:id
    div_elements = tree.xpath('//tei:div[@type="story"][@xml:id]', namespaces=NAMESPACES)

    for element in div_elements:
        # Extract the xml:id attribute
        xml_id = element.attrib.get(f'{{{XML_NAMESPACE}}}id') # for example: {'type': 'story', '{http://www.w3.org/XML/1998/namespace}id': 'Adat-Zadikim_0001'}
        assert xml_id is not None, "Could not find xml:id attribute"
        
        # Extract the text content of the <div> element (all inner text)
        text_content = ''.join(element.xpath('.//text()')).strip()
        assert text_content is not None, "Could not find text_content attribute"

        # Append the xml:id and the corresponding text to the list
        story_divs.append((xml_id, text_content))
    
    return story_divs


def standardize_text(raw_txt):
    # raw_txt = re.sub('״', '"', raw_txt)
    raw_txt = re.sub(r'\s*\.\s*', '.', raw_txt)
    raw_txt = raw_txt.strip()
    return raw_txt


def extract_ner_label_phrase_and_reconstruct_word(data: Dict) -> List[Dict]:
    ''' 
    Document this function: 
    Extract NER words from the given input data.
    
    '''

    if not all(key in data for key in ["tokens", "ner_entities"]):
        raise ValueError("The JSON data is missing required fields (text, tokens or ner_entities).")

    # Extract the tokens and ner_entities
    tokens = data.get('tokens')
    ner_entities = data.get('ner_entities')

    
    # Create a mapping of token indices to words
    position_to_token = {i: token['token'] for i, token in enumerate(tokens)}
    
    # Extract NER entities with corresponding words
    ner_results = []
    for entity in ner_entities:
        word = [position_to_token[i] for i in range(entity['token_start'], entity['token_end'] + 1)]
        ner_results.append({
            'label': entity['label'],
            'raw_ner_phrase': entity['phrase'],
            'word': ''.join(word),
            'start': entity['start'],
            'end': entity['end']
        })
    
    return ner_results


def extract_lemmatizaion_from_preds(preds: Dict[str, str]):
    return ' '.join([el['lex'] for pred in preds for el in pred['tokens']])


def extract_phrase_from_ner_preds(preds: Dict[str, str]):
    return [(el['raw_ner_phrase'], el['label']) for el in preds ]

def extract_word_from_ner_preds(preds: Dict[str, str]):
    return [(el['word'], el['label']) for el in preds ]


def extract_word_from_ner_preds_with_position(preds: Dict[str, str]):
    return [((el['start'], el['end']), (el['word'], el['label'])) for el in preds ]


def extract_segmentation_from_preds(preds: Dict[str, str]):
    return ' '.join([el['seg'] for pred in preds for el in pred['tokens']])


def parse_tokens_segmentation(tokens: List[Dict[str, str]]):
    seg_elems = []
    seg_tups = [] # segmented tups to return, for analysis purposes
    # offsets = []
    for token in tokens:
        cur_seg_tup = token['seg']
        offsets = token['offsets']
        match len(cur_seg_tup):
            case 1:
                seg_elems.append(cur_seg_tup[0])
            case 2:
                seg_elems.append(cur_seg_tup[1]) # assuming that in case of two segments, the first segment is a "BACHLAM", i.e. should be removed for lematization. 
                seg_tups.append(((offsets['start'], offsets['end']), cur_seg_tup))
            case L if L > 2:
                raise ValueError('greater than 2')
            case _:
                raise ValueError('value should be nice.')
    return ' '.join(seg_elems), seg_tups


def align_ner_with_segments(row):
    """ 
    
    todo: 
    1. remove redundancy
    2. convert to a more efficient data structure (dictionary for faster lookup) [=?]
    3. add some documentation
    4. input is not just a "row"

    """
    ner_data = row['ner_entities_by_word_with_positions']
    seg_data = row['seg_tups']

    ner_data_dict = {item[0]: item[1] for item in ner_data}
    seg_data_dict = {item[0][0]: item[1] for item in seg_data}

    # Create the mapping by matching keys
    mapping = {key: 
                (ner_data_dict[key], seg_data_dict[key[0]], (ner_data_dict[key][0].removeprefix(seg_data_dict[key[0]][0]), ner_data_dict[key][1])) 
                if key[0] in seg_data_dict 
                else (ner_data_dict[key], None, ner_data_dict[key])
                for key in ner_data_dict 
    }
    
    return mapping


def group_by_second_element(tup_list: list[tuple]) -> dict[List[str]]:
    # Create a dictionary to group by NER types
    ner_dict = {}
    for tup in tup_list:
        if not tup[1] in ner_dict.keys():
            ner_dict[tup[1]] = []
        ner_dict[tup[1]].append(tup[0])
    return ner_dict