/** Fits the entire remote desktop inside its viewport without changing its resolution. */
export function fitRdpScale(
  viewportWidth: number,
  viewportHeight: number,
  displayWidth: number,
  displayHeight: number,
  magnification = 1,
): number {
  const dimensions = [viewportWidth, viewportHeight, displayWidth, displayHeight];
  if (dimensions.some((value) => !Number.isFinite(value) || value <= 0)) return 1;

  const fit = Math.min(viewportWidth / displayWidth, viewportHeight / displayHeight);
  const zoom = Number.isFinite(magnification) && magnification > 0 ? magnification : 1;
  const scale = fit * zoom;
  return Number.isFinite(scale) && scale > 0 ? scale : 1;
}
