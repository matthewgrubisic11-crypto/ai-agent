# SPEC — Patrick: Half a Million

GOAL:    The viewer remembers one line: Patrick left Sydney for Shanghai to build an import business, and he has already put $500,000 into it.
OUTPUT:  HyperFrames, 1920 x 1080, 30 fps
TIME:    21 s x 30 = 630 frames. Silent for now (no music source signed in).

FACTS (from the person, verbatim meaning only):
- Name: Patrick. Route: Sydney -> Shanghai.
- Business: imports products into Australia and sells them at retail price.
- $500,000 = money he has ALREADY put in. Not a target, not revenue.
- Not claimed: one-way, own money vs investors, a company name, dates, product types, prices.

LOOK:
- Grounds are flat colour fields, one per object, no gradients, no texture:
  yellow #F5C518 (passport / home stage), cobalt #1F4FA3 (ticket), sky #BFD9EE (Shanghai),
  concrete #E4DFD6 (shop), paper #F7F5F0 (price tag / payoff).
- Ink #14213D. Paper ink #F7F5F0 on cobalt.
- Accent red #D7262E: ONLY on the dollar figures ($0, $500,000) and the end-card arrow.
- Display: Archivo Black. Hook "$0" 520 px; payoff "$500,000" 300 px; titles 76-96 px, tracking -1%.
- Body / ticket fields: Inter 700, 30-40 px.
- Medium: flat printed objects (passport stamp, boarding pass, shipping container, cardboard boxes, swing tags). Shadows: 0 18px 0 rgba(20,33,61,.18) hard offset, no blur.

OBJECTS:
- Passport stamp: rectangular double-ruled border, rotated -8 deg, "DEPARTED" / "SYDNEY".
- Boarding pass: white card, rounded 28 px, dashed perforation, stub on the right; SYDNEY -> SHANGHAI, PASSENGER PATRICK, plane glyph on the arrow.
- Shanghai skyline (Lujiazui): Oriental Pearl Tower (spheres on a stem), Jin Mao (stepped pagoda), SWFC (slab with the trapezoid hole), Shanghai Tower (tallest, tapered). River strip below.
- Shipping container: corrugated ribs, end doors, stencilled "SHANGHAI -> SYDNEY".
- Shop shelf: timber plank on brackets; kraft cardboard boxes, each with a white swing tag "RRP".

MOTION:
- enter: expo.out 0.5-0.7 s; titles per word blur 6px -> 0, 0.13 s, 0.067 s apart, no translate.
- camera/flood: power2.inOut 0.4 s. exits/zooms: power3.in, 40-50% shorter than entrances.
- stamp slam: scale 1.7 -> 1 in 0.22 s expo.out.
- number roll: per-digit wheel, 1.5 s power3.out, 0.06 s stagger, two revolutions.

SHOTS:
1. 0.0-3.0  yellow. "$0" in red already on screen (frame 0 = thumbnail). 0.8 stamp DEPARTED SYDNEY slams. 1.3 "Patrick leaves Sydney". 2.6 stamp zooms through, its cobalt fill floods the frame.
2. 3.0-7.0  cobalt. Boarding pass settles from 1.12 -> 1 out of the zoom. Arrow draws, plane flies, SHANGHAI lands 4.0. Hold. 6.2 pass tears on the perforation; pieces fly; sky floods up.
3. 7.0-10.6 sky. Skyline rises building by building. 7.7 "To start an import business". 9.7 container drops in on the skyline, 10.3 whips out left.
4. 10.6-14.6 concrete. Container whips in from the right and lands. Door swings, three boxes slide onto the shelf, tags swing. 11.9 "Sold at retail in Australia". 14.0 camera zooms through the middle RRP tag.
5. 14.6-18.2 paper. "$500,000" rolls in red, lands 16.1. 16.3 "Already invested". 17.8 blur out, yellow floods.
6. 18.2-21.0 yellow. PATRICK per letter, then "Sydney -> Shanghai" with a red arrow. Holds 2 s.

BANNED: dark void ground; glow, particles, gradients, glass; cream + serif + mono labels; everything fading up; three cards in a row; docked logo; titles moving after they land; counting up through invented intermediate amounts.

QA: f0 shows $0 and yellow; 4.5 s pass reads SYDNEY -> SHANGHAI; 8.5 s skyline reads as Shanghai; 13 s boxes on shelf + tags; 16.5 s $500,000 fully landed; 20 s PATRICK end card.
