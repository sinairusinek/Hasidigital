"""h2 is the keeper, but its fifth bubble shows only balance scales; the economic
historian needs his rising graph and coins back. Touch that one bubble only."""
import os, sys, json
from google import genai
from google.genai import types
for line in open('/Users/sinairusinek/Documents/GitHub/Hasidigital/.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1); os.environ.setdefault(k, v.strip().strip('"').strip("'"))
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, 'tbl_h2.png'), 'rb').read()
P = ("Edit this wood-engraving. Change ONE thing and nothing else: the fifth thought bubble, the rightmost one, "
     "above the man in the waistcoat at the right-hand end of the table. It currently contains only a pair of "
     "balance scales. Redraw the contents of that one bubble so it contains three things together, drawn small as "
     "simple engraved line emblems: a rising zig-zag line graph with an arrow at its upper end, a pair of balance "
     "scales beside it, and three small stacked coins beneath. Keep that bubble's outline and its trail of little "
     "circles exactly where they are. "
     "Everything else in the picture must stay pixel-for-pixel as it is: all five people, their faces, clothes and "
     "poses, the other four thought bubbles and their contents, the open Hebrew book, the table and every object "
     "on it, and the same black-ink wood-engraving style on warm cream paper. "
     "No letters, words or numbers anywhere, except the Hebrew already printed on the book's pages.")
for name in (sys.argv[1:] or ['tbl_k1']):
    r = client.models.generate_content(model='gemini-2.5-flash-image',
        contents=[types.Part.from_bytes(data=src, mime_type='image/png'), P])
    u = r.usage_metadata; ok = False
    for p in r.candidates[0].content.parts:
        if getattr(p,'inline_data',None) and p.inline_data.data:
            open(os.path.join(HERE, f'{name}.png'),'wb').write(p.inline_data.data); ok = True
    print(json.dumps(dict(name=name, saved=ok, prompt_tokens=u.prompt_token_count, output_tokens=u.candidates_token_count)))
