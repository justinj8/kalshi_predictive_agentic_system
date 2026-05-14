import { motion } from "framer-motion";

interface Props {
  /** Drives wheel-spin speed + body shake intensity, 0 (idle) .. 1 (full chat). */
  intensity?: number;
  className?: string;
}

/**
 * A detailed side-profile modern Formula 1 car in Scuderia Ferrari livery,
 * drawn as layered SVG. Facing right (the car launches to the right).
 *
 * Realism comes from tonal separation rather than cartoon outlines:
 * multi-stop gradients on every panel (key light catching the top edge,
 * deep shadow underneath), an exposed carbon-weave floor and wing elements,
 * ambient-occlusion gradients in the wheel wells, specular streaks on the
 * engine cover and halo, matte Pirelli rubber with a faint sidewall sheen,
 * and the Ferrari yellow shield + black airbox accents.
 *
 * viewBox 0 0 1200 420.
 */
export function F1Car({ intensity = 1, className }: Props) {
  // Wheel spin gets faster with intensity; at full chat the spokes smear.
  const i = Math.min(1, Math.max(0, intensity));
  const wheelDur = 0.9 - 0.78 * i; // 0.9s idle -> 0.12s launch
  const spokeOpacity = 0.55 - 0.45 * i;

  return (
    <svg
      viewBox="0 0 1200 420"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        {/* Exposed carbon-fibre weave for floor / wing elements */}
        <pattern
          id="carbon"
          width="6"
          height="6"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <rect width="6" height="6" fill="#0c0c10" />
          <rect width="3" height="3" fill="#17171d" />
          <rect x="3" y="3" width="3" height="3" fill="#17171d" />
        </pattern>

        {/* Ferrari Rosso Corsa — key-lit body */}
        <linearGradient id="ferrari" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ff4332" />
          <stop offset="22%" stopColor="#e51009" />
          <stop offset="62%" stopColor="#a60600" />
          <stop offset="100%" stopColor="#4c0200" />
        </linearGradient>

        {/* Engine cover — same red, a touch brighter where the light rakes */}
        <linearGradient id="cover" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ff5848" />
          <stop offset="38%" stopColor="#d80b04" />
          <stop offset="100%" stopColor="#5e0200" />
        </linearGradient>

        {/* Matte black accent panels (airbox surround, halo, mirrors) */}
        <linearGradient id="blackpanel" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3a3b42" />
          <stop offset="45%" stopColor="#15161a" />
          <stop offset="100%" stopColor="#050507" />
        </linearGradient>

        {/* Pirelli rubber */}
        <radialGradient id="rubber" cx="38%" cy="34%" r="75%">
          <stop offset="0%" stopColor="#34343a" />
          <stop offset="55%" stopColor="#161619" />
          <stop offset="100%" stopColor="#020203" />
        </radialGradient>

        {/* Wheel rim */}
        <radialGradient id="rim" cx="42%" cy="38%" r="65%">
          <stop offset="0%" stopColor="#e6e7ec" />
          <stop offset="45%" stopColor="#8c8d94" />
          <stop offset="100%" stopColor="#1c1c20" />
        </radialGradient>

        {/* Ground contact shadow */}
        <radialGradient id="contact" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="rgba(0,0,0,0.85)" />
          <stop offset="100%" stopColor="rgba(0,0,0,0)" />
        </radialGradient>

        {/* Specular streak */}
        <linearGradient id="spec" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="rgba(255,255,255,0)" />
          <stop offset="50%" stopColor="rgba(255,255,255,0.9)" />
          <stop offset="100%" stopColor="rgba(255,255,255,0)" />
        </linearGradient>

        <filter id="soft" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="1.1" />
        </filter>
      </defs>

      {/* ---- Ground contact shadows ---- */}
      <ellipse cx="300" cy="372" rx="150" ry="20" fill="url(#contact)" />
      <ellipse cx="940" cy="372" rx="150" ry="20" fill="url(#contact)" />
      <ellipse cx="620" cy="368" rx="320" ry="14" fill="url(#contact)" opacity="0.6" />

      {/* ---- REAR WING (far left) ---- */}
      <g>
        {/* endplate */}
        <path
          d="M96 168 L150 168 L150 330 L116 330 L104 250 Z"
          fill="url(#ferrari)"
          stroke="#000"
          strokeOpacity="0.4"
        />
        {/* main plane */}
        <path d="M92 176 L210 172 L210 196 L92 202 Z" fill="url(#carbon)" />
        <path d="M92 176 L210 172 L210 181 L92 185 Z" fill="url(#cover)" />
        {/* DRS upper flap */}
        <path d="M120 150 L208 148 L208 166 L120 168 Z" fill="url(#ferrari)" />
        <rect x="120" y="150" width="88" height="3" fill="url(#spec)" opacity="0.5" />
        {/* sponsor-strip hint */}
        <rect x="120" y="158" width="60" height="3.5" fill="#f4d000" opacity="0.85" />
      </g>

      {/* ---- FLOOR / PLANK ---- */}
      <path
        d="M170 312 L1000 304 L1070 326 L1050 338 L210 344 L160 330 Z"
        fill="url(#carbon)"
        stroke="#000"
        strokeOpacity="0.5"
      />
      <path d="M210 318 L1000 311 L1000 318 L220 326 Z" fill="#000" opacity="0.55" />

      {/* ---- ENGINE COVER + SIDEPOD (mid body) ---- */}
      <path
        d="M150 250 C 150 250 250 196 360 188 C 470 180 520 182 560 188
           L600 250 C 600 250 560 300 470 312 C 360 322 220 320 175 300
           C 150 288 150 250 150 250 Z"
        fill="url(#cover)"
        stroke="#000"
        strokeOpacity="0.45"
      />
      {/* sidepod undercut shadow */}
      <path
        d="M210 300 C 320 318 430 318 520 300 C 470 312 360 322 250 312 Z"
        fill="#000"
        opacity="0.55"
      />
      {/* black sponsor band along the cover */}
      <path
        d="M205 232 C 300 210 410 206 520 214 L518 228 C 410 220 305 224 213 244 Z"
        fill="url(#blackpanel)"
      />
      {/* Ferrari yellow shield accent */}
      <g transform="translate(430 224)">
        <path d="M0 0 L26 0 L26 16 L13 24 L0 16 Z" fill="#f4d000" />
        <path d="M3 3 L23 3 L23 14 L13 20 L3 14 Z" fill="#1d1d1d" opacity="0.85" />
        {/* tiny prancing-horse suggestion */}
        <path
          d="M9 16 C 9 11 11 8 13 7 C 12 10 14 10 16 8 C 16 12 14 16 13 17 Z"
          fill="#f4d000"
        />
      </g>
      {/* specular streak */}
      <path
        d="M230 214 C 330 198 430 196 520 204"
        fill="none"
        stroke="url(#spec)"
        strokeWidth="3"
        opacity="0.7"
        filter="url(#soft)"
      />

      {/* ---- AIRBOX intake (behind driver head) ---- */}
      <path
        d="M520 200 C 540 150 575 150 596 168 L600 250 L520 250 Z"
        fill="url(#blackpanel)"
        stroke="#000"
        strokeOpacity="0.4"
      />
      <ellipse cx="556" cy="178" rx="13" ry="16" fill="#000" opacity="0.9" />

      {/* ---- COCKPIT / SURVIVAL CELL ---- */}
      <path
        d="M560 250 C 560 250 575 205 660 198 C 760 190 880 210 905 250
           L905 270 L560 270 Z"
        fill="url(#ferrari)"
        stroke="#000"
        strokeOpacity="0.4"
      />
      {/* black cockpit-rim accent */}
      <path
        d="M576 244 C 600 214 670 206 760 204 C 830 203 880 218 900 246"
        fill="none"
        stroke="url(#blackpanel)"
        strokeWidth="9"
      />

      {/* driver helmet */}
      <g>
        <ellipse cx="668" cy="210" rx="30" ry="29" fill="#0d0d12" />
        <path
          d="M644 206 C 650 192 686 192 692 206 C 694 214 690 220 668 221
             C 650 221 643 214 644 206 Z"
          fill="#f4d000"
        />
        <path d="M652 197 L684 197 L680 205 L656 205 Z" fill="#e51009" />
        {/* visor */}
        <path
          d="M648 210 C 656 204 682 204 690 210 C 686 218 654 218 648 210 Z"
          fill="#0a1a22"
        />
        <path
          d="M650 209 C 658 206 678 206 686 209"
          stroke="rgba(120,200,220,0.75)"
          strokeWidth="1.6"
          fill="none"
        />
      </g>

      {/* ---- HALO ---- */}
      <path
        d="M610 250 C 610 250 612 186 700 172 C 800 158 858 196 868 250"
        fill="none"
        stroke="#101015"
        strokeWidth="13"
        strokeLinecap="round"
      />
      <path
        d="M610 250 C 610 250 612 186 700 172 C 800 158 858 196 868 250"
        fill="none"
        stroke="url(#spec)"
        strokeWidth="3"
        strokeLinecap="round"
        opacity="0.6"
      />
      {/* halo center strut */}
      <path d="M704 172 L704 210" stroke="#101015" strokeWidth="9" strokeLinecap="round" />

      {/* ---- NOSE CONE ---- */}
      <path
        d="M905 252 C 905 252 980 248 1060 268 C 1120 282 1150 300 1150 300
           L1150 312 C 1150 312 1070 300 1000 298 C 950 297 905 296 905 296 Z"
        fill="url(#ferrari)"
        stroke="#000"
        strokeOpacity="0.4"
      />
      {/* black nose-tip + livery break */}
      <path
        d="M1090 286 C 1115 290 1138 298 1150 302 L1150 312 C 1138 308 1112 300 1086 297 Z"
        fill="url(#blackpanel)"
      />
      <path
        d="M930 266 C 1000 264 1060 274 1110 290"
        fill="none"
        stroke="#f4d000"
        strokeWidth="4"
        opacity="0.85"
      />

      {/* ---- FRONT WING (far right) ---- */}
      <g>
        {/* endplate */}
        <path
          d="M1150 286 L1178 286 L1184 348 L1150 350 Z"
          fill="url(#ferrari)"
          stroke="#000"
          strokeOpacity="0.4"
        />
        {/* stacked elements */}
        <path d="M1050 322 L1182 318 L1184 330 L1052 334 Z" fill="url(#carbon)" />
        <path d="M1060 334 L1184 330 L1186 342 L1062 346 Z" fill="url(#carbon)" />
        <path d="M1050 322 L1182 318 L1183 324 L1051 328 Z" fill="url(#cover)" />
      </g>

      {/* ---- TYRES ---- */}
      <Wheel cx={300} cy={290} r={82} dur={wheelDur} spokeOpacity={spokeOpacity} />
      <Wheel cx={940} cy={290} r={80} dur={wheelDur} spokeOpacity={spokeOpacity} />

      {/* ---- exhaust glow hint ---- */}
      <ellipse cx="150" cy="262" rx="11" ry="7" fill="#ff6a2c" opacity="0.6" filter="url(#soft)" />
    </svg>
  );
}

function Wheel({
  cx,
  cy,
  r,
  dur,
  spokeOpacity,
}: {
  cx: number;
  cy: number;
  r: number;
  dur: number;
  spokeOpacity: number;
}) {
  return (
    <g>
      {/* tyre */}
      <circle cx={cx} cy={cy} r={r} fill="url(#rubber)" />
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke="#000"
        strokeOpacity="0.7"
        strokeWidth="2"
      />
      {/* Pirelli sidewall band hint */}
      <circle
        cx={cx}
        cy={cy}
        r={r * 0.78}
        fill="none"
        stroke="#f4d000"
        strokeOpacity="0.28"
        strokeWidth="2"
      />
      {/* sidewall sheen */}
      <ellipse
        cx={cx - r * 0.28}
        cy={cy - r * 0.3}
        rx={r * 0.5}
        ry={r * 0.34}
        fill="rgba(255,255,255,0.05)"
      />
      {/* spinning rim */}
      <motion.g
        animate={{ rotate: 360 }}
        transition={{ duration: dur, ease: "linear", repeat: Infinity }}
        style={{ originX: `${cx}px`, originY: `${cy}px` }}
      >
        <circle cx={cx} cy={cy} r={r * 0.52} fill="url(#rim)" />
        <circle cx={cx} cy={cy} r={r * 0.52} fill="none" stroke="#0a0a0c" strokeWidth="2" />
        {[0, 60, 120, 180, 240, 300].map((a) => (
          <rect
            key={a}
            x={cx - 2}
            y={cy - r * 0.5}
            width="4"
            height={r * 0.42}
            fill="#0c0c10"
            opacity={spokeOpacity}
            transform={`rotate(${a} ${cx} ${cy})`}
          />
        ))}
        <circle cx={cx} cy={cy} r={r * 0.13} fill="#e6e7ec" />
        <circle cx={cx} cy={cy} r={r * 0.13} fill="none" stroke="#000" strokeWidth="1.5" />
      </motion.g>
      {/* brake-heat glow */}
      <circle cx={cx} cy={cy} r={r * 0.3} fill="#ff5a1e" opacity="0.2" />
    </g>
  );
}
