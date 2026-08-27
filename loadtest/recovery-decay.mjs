export function decayedComplaintRatio(baseRatio, secondsSinceFailure, decaySeconds) {
  if (decaySeconds === 0 || secondsSinceFailure >= decaySeconds) return 0;
  return baseRatio * (1 - secondsSinceFailure / decaySeconds);
}
