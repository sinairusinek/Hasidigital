import os, sys, json
from google import genai
from google.genai import types
for line in open('/Users/sinairusinek/Documents/GitHub/Hasidigital/.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1); os.environ.setdefault(k, v.strip().strip('"').strip("'"))
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, 'm1_press_engraving.png'), 'rb').read()
SHT = ("Replace the hat on top of the machine with a Hasidic SHTREIMEL, drawn in the same engraving style: "
       "seen from a low three-quarter angle, it is a huge flat round fur hat shaped like a thick fur doughnut or a fur tyre lying flat, "
       "about three times wider than it is tall, made of many dark sable tails arranged radially around the rim, "
       "with only a small flat black velvet skullcap visible in the centre, barely rising above the fur. "
       "It has NO brim and NO crown sticking up: it is not a bowler, not a top hat, not a fedora, not a cylinder. "
       "Keep the curly side-locks hanging below it. ")
REST = ("Remove the three small cards flying out on the right and their speed lines completely, leaving clean empty cream paper there "
        "(more empty space to the upper right). Keep everything else exactly as it is: the press, gears, steam, the paper strip going in, "
        "the flapping black coat tails, the style and the paper. No text anywhere.")
V = {'s1': SHT + REST, 's2': SHT + "The fur ring should be clearly wider than the whole top of the machine, overhanging it on both sides. " + REST}
for name in (sys.argv[1:] or list(V)):
    r = client.models.generate_content(model='gemini-2.5-flash-image', contents=[types.Part.from_bytes(data=src, mime_type='image/png'), V[name]])
    u = r.usage_metadata; ok = False
    for p in r.candidates[0].content.parts:
        if getattr(p, 'inline_data', None) and p.inline_data.data:
            open(os.path.join(HERE, f'm1_{name}.png'), 'wb').write(p.inline_data.data); ok = True
    print(json.dumps(dict(name=name, saved=ok, prompt_tokens=u.prompt_token_count, output_tokens=u.candidates_token_count)))
