import { defineSegment, type Segment } from "videowright";
import "./scene.css";

const EASE_OUT = "cubic-bezier(0.22, 1, 0.36, 1)";
const REVEAL_MS = 500;
const STAGGER_MS = 90;

/** The recovery lifecycle, in the order the pipeline runs it. */
export const LOOP_STAGES = [
	"Baseline",
	"Detect",
	"Propose",
	"Approve",
	"Roll back",
	"Verify",
];

interface SceneSpec {
	id: string;
	advances: number[];
	voiceover: string;
	html: string;
}

/** Resolves when each font face that the style declares is loaded, so no frame shows a fallback font. */
function fontsReady(): Promise<unknown> {
	return Promise.all([...document.fonts].map((face) => face.load()));
}

function revealBeat(root: HTMLElement, beat: number): void {
	const elements = root.querySelectorAll<HTMLElement>(`[data-beat="${beat}"]`);
	elements.forEach((element, index) => {
		// element.animate() is the only animation that the render clock drives.
		element.animate(
			[
				{ opacity: 0, transform: "translateY(24px)" },
				{ opacity: 1, transform: "translateY(0)" },
			],
			{
				duration: REVEAL_MS,
				delay: index * STAGGER_MS,
				easing: EASE_OUT,
				fill: "forwards",
			},
		);
	});
}

/**
 * A segment that shows `html` and reveals its `data-beat` groups in order.
 * Beat 0 shows at once. Each later beat waits for the next advance, so markup with
 * beats 0 to N needs N + 1 entries in `advances`: N reveals and the end of the segment.
 */
export function defineScene(spec: SceneSpec): Segment {
	let host: HTMLElement | null = null;
	return defineSegment({
		id: spec.id,
		advances: spec.advances,
		voiceover: spec.voiceover,

		async mount(el) {
			host = el;
			el.innerHTML = spec.html;
			await fontsReady();
		},

		async play(ctx) {
			const root = host;
			if (!root) return;
			const beats = [...root.querySelectorAll<HTMLElement>("[data-beat]")].map(
				(element) => Number(element.dataset.beat),
			);
			revealBeat(root, 0);
			for (let beat = 1; beat <= Math.max(...beats); beat++) {
				await ctx.waitForNext();
				revealBeat(root, beat);
			}
		},

		unmount() {
			host = null;
		},
	});
}

/**
 * The six lifecycle stages as a bar, with stage `active` (0 to 5) highlighted.
 * Two bars in one `.stage-stack` occupy the same place, so a later beat can move
 * the highlight without the row shifting.
 */
export function loopBar(active: number, beat = 0): string {
	const steps = LOOP_STAGES.map((name, index) => {
		const state = index === active ? " active" : index < active ? " done" : "";
		return `<div class="step${state}">${name}</div>`;
	}).join("");
	return `<div class="loop" data-beat="${beat}">${steps}</div>`;
}

function icon(path: string): string {
	return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

export const checkIcon = icon("M4 12.5 9.5 18 20 6.5");
export const arrowIcon = icon("M3 12h17m-6-6.5 6.5 6.5-6.5 6.5");
export const eyeIcon = icon(
	"M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Zm10 2.6a2.6 2.6 0 1 0 0-5.2 2.6 2.6 0 0 0 0 5.2Z",
);

/**
 * A real screenshot in a browser-like frame. `alt` must describe what the screen
 * actually shows, because the frame is evidence and not decoration.
 */
export function shot(src: string, alt: string, beat = 0, extraClass = ""): string {
	return `<figure class="shot ${extraClass}" data-beat="${beat}"><img src="${src}" alt="${alt}"></figure>`;
}

/** A label and a value from a real run, as one fact row. */
export function fact(label: string, value: string, tone = ""): string {
	return `<div class="fact-label">${label}</div><div class="fact-value ${tone}">${value}</div>`;
}
