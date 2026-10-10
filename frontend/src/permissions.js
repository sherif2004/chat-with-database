/** Whether the signed-in user's role grants a permission. The backend is the
 *  authority; this only decides what the interface offers. */
export function can(user, permission) {
  return Boolean(user?.permissions?.includes(permission));
}
