"""Remove the one stray card with garbled pseudo-lettering from the f2 plate.
Everything else must stay byte-for-byte in look: same figures, same style."""
import os, sys, json
from google import genai
from google.genai import types

for line in open('/Users/sinairusinek/Documents/GitHub/Hasidigital/.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, 'f2.png'), 'rb').read()

P = ("Edit this wood-engraving. Keep ALL FIVE scholars, their faces, poses, clothing and props, the five thought "
     "bubbles above them, the big open book in the centre of the round table, the table, the chairs, the stacks of "
     "books, the candle, the scrolls and the ledger exactly as they are, in exactly the same 19th-century "
     "black-ink wood-engraving style on warm cream paper. "
     "Change ONE thing only: the small upright card or framed picture standing on the table near the right-hand "
     "side, which carries scribbled marks that look like unreadable writing. Remove that card completely and fill "
     "the space with the plain engraved table top, matching the surrounding wood grain and hatching. "
     "ABSOLUTELY NO LETTERS, WORDS, NUMBERS OR WRITING ANYWHERE IN THE IMAGE: the marks on the open book's pages "
     "and on all other papers must remain purely abstract squiggles that are clearly not letters.")

for name in (sys.argv[1:] or ['c1']):
    r = client.models.generate_content(model='gemini-2.5-flash-image',
                                       contents=[types.Part.from_bytes(data=src, mime_type='image/png'), P])
    u = r.usage_metadata; ok = False
    for p in r.candidates[0].content.parts:
        if getattr(p, 'inline_data', None) and p.inline_data.data:
            open(os.path.join(HERE, f'{name}.png'), 'wb').write(p.inline_data.data); ok = True
    print(json.dumps(dict(name=name, saved=ok, prompt_tokens=u.prompt_token_count,
                          output_tokens=u.candidates_token_count)))
