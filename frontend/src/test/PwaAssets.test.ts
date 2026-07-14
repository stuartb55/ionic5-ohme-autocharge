/// <reference types="node" />

import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const SCREENSHOTS = [
  {
    file: 'screenshot-wide.png',
    width: 1280,
    height: 720,
    sha256: 'bb466a74cd8d72f08742877f3e241b9e17435dc2a2fe34d2866f12bbdc82c2e5',
  },
  {
    file: 'screenshot-narrow.png',
    width: 720,
    height: 1280,
    sha256: 'ff1fa453eba7dd5da4184372c8424b38b705d23740770570cd3d8033e6b3456c',
  },
];

describe('PWA screenshot baselines', () => {
  it.each(SCREENSHOTS)('keeps $file at its reviewed dimensions and pixels', (screenshot) => {
    const image = readFileSync(resolve('public', screenshot.file));

    // PNG IHDR stores width and height at byte offsets 16 and 20.
    expect(image.subarray(1, 4).toString()).toBe('PNG');
    expect(image.readUInt32BE(16)).toBe(screenshot.width);
    expect(image.readUInt32BE(20)).toBe(screenshot.height);
    expect(createHash('sha256').update(image).digest('hex')).toBe(screenshot.sha256);
  });
});
