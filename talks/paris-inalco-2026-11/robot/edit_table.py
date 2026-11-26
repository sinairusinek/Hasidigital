"""Fix the pilot: t2 has the best composition but only FOUR scholars -- the economic
historian was dropped and his thought bubble merged into the theologian's. Edit t2 to
add the fifth figure and give each of the five his own bubble."""
import os, sys, json
from google import genai
from google.genai import types

for line in open('/Users/sinairusinek/Documents/GitHub/Hasidigital/.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else 't2.png'), 'rb').read()

KEEP = ("Keep the existing four scholars exactly as they are -- the old bearded man with spectacles and the "
        "magnifying glass on the far left, the traveller in the field coat with the walking staff, the young man "
        "in the pale turtleneck holding the dividers, and the robed scholar in the skullcap -- with their faces, "
        "poses and props unchanged. Keep the big open book in the centre of the round table, the stacks of folios, "
        "the open card-index drawer, the abacus, the coins, the candle and the rolled charts. Keep exactly the same "
        "19th-century wood-engraving style, black ink cross-hatching on warm cream paper. ")

NOTEXT = ("ABSOLUTELY NO LETTERS, WORDS, NUMBERS, LABELS OR CAPTIONS ANYWHERE IN THE IMAGE. Everything written on "
          "pages, book spines, cards and charts must be only abstract squiggles and ruled lines, never readable text.")

BASE = (KEEP +
    "Make these changes. "
    "1) ADD A FIFTH SCHOLAR, seated at the right-hand end of the table so that five scholars sit in an arc around "
    "the one book, all five faces visible and all five leaning in towards the same open book. The new fifth scholar "
    "is an ECONOMIC HISTORIAN: a brisk, clean-shaven man in a buttoned waistcoat with his shirtsleeves rolled up, "
    "a pencil behind his ear, one hand resting on a thick ledger and the other on a rolled graph; the abacus and the "
    "stacks of coins belong to him and sit by his place. "
    "2) GIVE EACH OF THE FIVE HIS OWN SEPARATE THOUGHT BUBBLE, five bubbles in all, evenly spaced across the top of "
    "the plate, each joined by its own trail of little circles to the head of its own scholar. Split the crowded "
    "right-hand bubble into two distinct bubbles. The five bubbles contain, from left to right: "
    "(a) a chain of small books linked one after another in a line, like a genealogy of editions; "
    "(b) a globe with the same little story symbol repeated on several different continents, joined by faint lines; "
    "(c) an abstract diagram of the story: a row of empty boxes joined by arrows above a small branching tree; "
    "(d) rays of light descending from a cloud onto a small open book, with a ladder rising towards the cloud; "
    "(e) a rising line graph with a pair of scales and a few coins beneath it. " + NOTEXT)

V = {
 'f1': BASE,
 'f2': BASE + " Widen the composition into a horizontal panoramic plate so the five seated scholars and the five "
       "bubbles above them all have room, with comfortable cream margins at the left and right edges.",
}
for name in (sys.argv[2:] or list(V)):
    r = client.models.generate_content(model='gemini-2.5-flash-image',
                                       contents=[types.Part.from_bytes(data=src, mime_type='image/png'), V[name]])
    u = r.usage_metadata; ok = False
    for p in r.candidates[0].content.parts:
        if getattr(p, 'inline_data', None) and p.inline_data.data:
            open(os.path.join(HERE, f'{name}.png'), 'wb').write(p.inline_data.data); ok = True
    print(json.dumps(dict(name=name, saved=ok, prompt_tokens=u.prompt_token_count,
                          output_tokens=u.candidates_token_count)))
