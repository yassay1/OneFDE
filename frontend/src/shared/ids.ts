/** Engagement / Task / Run 等路径参数均为 UUID。非法值不得发往 API。 */
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isUuid(value: string | null | undefined): value is string {
  return Boolean(value && UUID_RE.test(value.trim()));
}

export function uuidOrEmpty(value: string | null | undefined): string {
  return isUuid(value) ? value.trim() : "";
}
