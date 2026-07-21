
def chunk_text_by_tokens(text, tokenizer, max_tokens=512):
    """
    Chunk text into segments, ensuring each segment is within the max token limit.
    
    Args:
        text (str): The input text to be chunked.
        tokenizer: The tokenizer instance from the Hugging Face Transformers library.
        max_tokens (int): The maximum number of tokens allowed in each chunk.
    
    Returns:
        List of tuples: Each tuple contains a chunk of text and the index of its first character in the original text.
    """
    
    # Tokenize the input text
    tokens = tokenizer(text, return_offsets_mapping=True, truncation=False)
    input_ids = tokens["input_ids"]
    offsets = tokens["offset_mapping"]

    # Remove special tokens if they exist (e.g., CLS/SEP)
    special_tokens = tokenizer.build_inputs_with_special_tokens([])
    num_special_tokens = len(special_tokens)
    max_tokens -= num_special_tokens  # Reserve space for special tokens

    chunks = []
    start_idx = 0

    while start_idx < len(input_ids):
        end_idx = start_idx + max_tokens
        chunk_tokens = input_ids[start_idx:end_idx]
        chunk_offsets = offsets[start_idx:end_idx]

        # Get the character offsets for the chunk
        char_start = chunk_offsets[0][0]
        char_end = chunk_offsets[-1][1]
        
        # Decode tokens back into text
        chunk_text = tokenizer.decode(chunk_tokens, skip_special_tokens=True) #.strip()
        # chunk_text = re.sub(r'##', '', tokenizer.decode(chunk_tokens, skip_special_tokens=True).strip())

        # Add the chunk and its starting character index
        chunks.append((chunk_text, char_start))

        # Move to the next chunk
        start_idx = end_idx

    return chunks


def chunk_text_by_tokens_and_sentences(text, tokenizer, max_tokens=512):
    """
    Chunk text into segments at sentence boundaries, ensuring each segment is within the max token limit.
    Returns original text segments.
    
    Args:
        text (str): The input text to be chunked.
        tokenizer: The tokenizer instance from the Hugging Face Transformers library.
        max_tokens (int): The maximum number of tokens allowed in each chunk.
    
    Returns:
        List of tuples: Each tuple contains (original_text_chunk, start_char_index)
    """
    if not text:
        return []

    # Tokenize the input text
    tokens = tokenizer(text, return_offsets_mapping=True, truncation=False)
    input_ids = tokens["input_ids"]
    offsets = tokens["offset_mapping"]

    if not input_ids or not offsets:
        return [(text, 0)]

    # Remove special tokens if they exist
    special_tokens = tokenizer.build_inputs_with_special_tokens([])
    num_special_tokens = len(special_tokens)
    max_tokens = max(1, max_tokens - num_special_tokens)  # Ensure at least 1 token

    chunks = []
    start_idx = 0

    while start_idx < len(input_ids):
        # Calculate the maximum possible end index for this chunk
        end_idx = min(start_idx + max_tokens, len(input_ids))
        
        if start_idx >= end_idx:
            break
            
        # Get character offsets for this range
        chunk_offsets = offsets[start_idx:end_idx]
        if not chunk_offsets:
            break
            
        char_start = chunk_offsets[0][0]
        char_end = chunk_offsets[-1][1]
        
        # If we're not at the end of the text, try to find a sentence boundary
        if end_idx < len(input_ids):
            current_text = text[char_start:char_end]
            last_period_idx = current_text.rfind('.')
            
            if last_period_idx != -1:
                # Found a period - adjust the end index
                new_char_end = char_start + last_period_idx + 1
                
                # Find the corresponding token index
                for i, (_, end) in enumerate(chunk_offsets):
                    if end > new_char_end:
                        end_idx = start_idx + i
                        char_end = new_char_end
                        break
            else:
                # No period found - try to find a space
                last_space_idx = current_text.rfind(' ')
                if last_space_idx != -1:
                    new_char_end = char_start + last_space_idx + 1
                    for i, (_, end) in enumerate(chunk_offsets):
                        if end > new_char_end:
                            end_idx = start_idx + i
                            char_end = new_char_end
                            break

        # Extract the original text segment
        original_chunk = text[char_start:char_end].strip()
        if original_chunk:  # Only add non-empty chunks
            chunks.append((original_chunk, char_start))
        
        # Move to the next chunk
        start_idx = end_idx

    # Handle any remaining text
    if not chunks:
        return [(text, 0)]
        
    # Check if we missed any text at the end
    last_chunk_end = chunks[-1][0][len(chunks[-1][0])]
    if last_chunk_end < len(text):
        remaining_text = text[last_chunk_end:].strip()
        if remaining_text:
            chunks.append((remaining_text, last_chunk_end))

    return chunks

# def split_text_to_chunks_with_indices(plain_text, chunk_size=2048):
#     chunks = []
#     start = 0

#     while start < len(plain_text):
#         # Find the end index for the chunk
#         end = min(start + chunk_size, len(plain_text))

#         # Adjust to find the nearest period
#         if end < len(plain_text):
#             period_index = plain_text.rfind('.', start, end)
#             if period_index != -1:
#                 end = period_index + 1  # Include the period

#         # Append the chunk and its starting index as a tuple
#         chunks.append((plain_text[start:end].strip(), start))

#         # Update the starting point for the next chunk
#         start = end

#     return chunks




def chunk_text_by_tokens_and_sentences(text, tokenizer, max_tokens=512):
    """
    Chunk text into segments at sentence boundaries, ensuring each segment is within the max token limit.
    Returns original text segments.
    
    Args:
        text (str): The input text to be chunked.
        tokenizer: The tokenizer instance from the Hugging Face Transformers library.
        max_tokens (int): The maximum number of tokens allowed in each chunk.
    
    Returns:
        List of tuples: Each tuple contains (original_text_chunk, start_char_index)
    """
    if not text:
        return []

    # Tokenize the input text

    # from utils import catch_sequence_length
    # with catch_sequence_length():  # TODO: Fix catch_sequence_length
    tokens = tokenizer(text, return_offsets_mapping=True, truncation=False)
    print('IGNORE MSG::: Token indices sequence length is longer than the specified maximum sequence length for this model')

    input_ids = tokens["input_ids"]
    offsets = tokens["offset_mapping"]

    if not input_ids or not offsets:
        return [(text, 0)]

    # Remove special tokens if they exist
    special_tokens = tokenizer.build_inputs_with_special_tokens([])
    num_special_tokens = len(special_tokens)
    max_tokens = max(1, max_tokens - num_special_tokens)  # Ensure at least 1 token

    chunks = []
    start_idx = 0

    while start_idx < len(input_ids):
        # Calculate the maximum possible end index for this chunk
        end_idx = min(start_idx + max_tokens, len(input_ids))
        
        if start_idx >= end_idx:
            break
            
        # Get character offsets for this range
        chunk_offsets = offsets[start_idx:end_idx]
        if not chunk_offsets:
            break
            
        char_start = chunk_offsets[0][0]
        char_end = chunk_offsets[-1][1]
        
        # If we're not at the end of the text, try to find a sentence boundary
        if end_idx < len(input_ids):
            current_text = text[char_start:char_end]
            last_period_idx = current_text.rfind('.')
            
            if last_period_idx != -1:
                # Found a period - adjust the end index
                new_char_end = char_start + last_period_idx + 1
                
                # Find the corresponding token index
                for i, (_, end) in enumerate(chunk_offsets):
                    if end > new_char_end:
                        end_idx = start_idx + i
                        char_end = new_char_end
                        break
            else:
                # No period found - try to find a space
                last_space_idx = current_text.rfind(' ')
                if last_space_idx != -1:
                    new_char_end = char_start + last_space_idx + 1
                    for i, (_, end) in enumerate(chunk_offsets):
                        if end > new_char_end:
                            end_idx = start_idx + i
                            char_end = new_char_end
                            break

        # Extract the original text segment
        original_chunk = text[char_start:char_end] #.strip()
        if original_chunk:  # Only add non-empty chunks
            chunks.append((original_chunk, char_start))
        
        # Move to the next chunk
        start_idx = end_idx

    # Handle any remaining text
    if not chunks:
        return [(text, 0)]
        
    # Check if we missed any text at the end
    last_chunk_end = chunks[-1][1] + len(chunks[-1][0])  # Use start index + length of chunk
    if last_chunk_end < len(text):
        remaining_text = text[last_chunk_end:] #.strip()
        if remaining_text:
            chunks.append((remaining_text, last_chunk_end))

    return chunks


def adjust_offsets_and_ner_positions(preds, start_idx):
    """
    Adjust the start and end offsets of tokens in the predictions by adding start_idx.
    
    Args:
        preds (dict): The predictions dictionary containing tokens with offsets.
        start_idx (int): The starting index to adjust offsets.
    
    Returns:
        dict: The updated predictions dictionary with adjusted offsets.

    TODO: update token positions within NER data? 
        - add raw / chunk position, or start_idx. 
    """
    for token in preds.get('tokens', []):
        offsets = token.get('offsets', {})
        if 'start' in offsets:
            offsets['start'] += start_idx
        if 'end' in offsets:
            offsets['end'] += start_idx

    for ner_entitity in preds.get('ner_entities', []):
        ner_entitity['start'] += start_idx
        ner_entitity['end'] += start_idx
        
    return preds


def assert_so_and_view_alignment(so, view, view_ind_start, view_ind_end):
    """ 
    TODO : add assertions of the TEXT within the entity information. 
    
    """

    # so.plain[view.get_table_pos(entity["start"]) : view.get_table_pos(entity["end"])]
    txt_view = view.get_plain()[view_ind_start: view_ind_end]
    txt_so = so.plain[view.get_table_pos(view_ind_start) : view.get_table_pos(view_ind_end)]   
    
    txt_view = "".join(txt_view.split())
    txt_so = "".join(txt_so.split())
    
    assert txt_view == txt_so, f"view should match SO\ntxt_view = {txt_view} ({len(txt_view)})\ntxt_so = {txt_so} ({len(txt_so)})"
