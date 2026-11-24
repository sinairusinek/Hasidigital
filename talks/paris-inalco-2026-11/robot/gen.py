import os, sys, json
from google import genai

for line in open('/Users/sinairusinek/Documents/GitHub/Hasidigital/.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))
key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
client = genai.Client(api_key=key)
MODEL = 'gemini-2.5-flash-image'
OUT = os.path.dirname(os.path.abspath(__file__))

COMMON = ("Illustration for an academic talk on digital humanities and Hasidic stories. It is a MACHINE, not a robot or android: "
          "no face, no eyes, no human body, no arms or legs. The only Hasidic signs are three: a round brown fur shtreimel hat sitting on top of the machine, "
          "two long curly side-locks (peyes) hanging down from either side of the top, and the black tails of a long coat (kapote) flapping out behind the machine "
          "as if in a wind. Respectful and witty, no caricature. No letters, words, numbers or signatures anywhere in the image. "
          "Plain warm cream paper background, the whole machine centred with generous margins.")
PROMPTS = {
 'm1_press_engraving': "A 19th-century wood-engraving, black ink cross-hatching on cream paper, like a plate in an old book of inventions: "
   "a cast-iron hand printing press and steam contraption with gears, rollers and a crank; loose paper story leaves feed in on one side "
   "and small index cards fly out on the other. ",
 'm2_card_engine': "A precise Victorian patent-drawing style engraving in black ink: a tall calculating engine of brass columns, toothed wheels and punched cards, "
   "like a Jacquard loom crossed with a difference engine; a chain of punched cards runs through it. ",
 'm3_pencil': "A loose graphite pencil sketch with a few red pencil notes-without-words (arrows, circles) and one swipe of yellow highlighter, like a scholar's marginal doodle: "
   "a boxy contraption of gears, a funnel hopper on top and a slot below; pages go into the hopper, slips come out of the slot; "
   "the yellow highlighter swipe marks one of the slips. ",
 'm4_tin': "A vintage painted tin toy machine, flat front view, slight wear on the paint: black, brass and grey tin with one yellow accent, "
   "a boxy body with a wind-up key, a big gear wheel, a crank and a paper slot. ",
}
which = sys.argv[1:] or list(PROMPTS)
log = []
for name in which:
    r = client.models.generate_content(model=MODEL, contents=PROMPTS[name] + COMMON)
    u = r.usage_metadata
    saved = False
    for part in r.candidates[0].content.parts:
        if getattr(part, 'inline_data', None) and part.inline_data.data:
            open(os.path.join(OUT, name + '.png'), 'wb').write(part.inline_data.data); saved = True
    rec = dict(name=name, saved=saved, prompt_tokens=u.prompt_token_count, output_tokens=u.candidates_token_count,
               thinking=getattr(u, 'thoughts_token_count', None), total=u.total_token_count)
    print(json.dumps(rec)); log.append(rec)
json.dump(log, open(os.path.join(OUT, 'usage.json'), 'a'))
