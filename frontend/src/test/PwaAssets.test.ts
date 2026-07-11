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
    sha256: '885ba4b004b0efbee09cad7a4bfc58b47b17d771f9d2d2b59444896be507b3a7',
  },
  {
    file: 'screenshot-narrow.png',
    width: 720,
    height: 1280,
    sha256: '46b20999d0f35eae052587408fd4d52aad181e844086b4a3bbb2e6a4f85b008d',
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
