Native navigation and form references
====================================

The provider Resource Explorer includes the checked-in native design from
``visual_admin/navigation_design.json``. Each endpoint renders its own engine
branch. Template nodes are presentation identities, never fabricated provider
resource IDs. Actual resources bind by kind and observed parent identity or
provider display path. Conditional branches require observed objects; this
conservative rule may hide supported branches until discovery supplies evidence.
Refresh/load-more retains the existing provider discovery boundary.

Selecting a bound object opens its object inspector. Definition children can
open the owner's specific tab. Unimplemented destinations open a numbered,
non-executing placeholder with engine, endpoint, owner and template context.
Context menus expose provider-declared object operations and scoped creation or
metadata placeholders; a placeholder never grants a capability.

``static/js/cdeadmin_ui/navigation/formReferences.json`` is the append-only form
reference registry. References identify reusable forms, not object instances.
Never renumber, recycle or derive IDs from render order. Existing common forms
(workspace, inspector, query editor, scripts, server/database setup and native
operation forms) display their shared reference. Missing native forms retain
their designated reference when the UX team implements them. Scoped creation and
metadata extraction each have their own reusable placeholder reference.

The native tree supplements the existing live browser/discovery tree. Its
unbound branches describe the design; they do not claim those objects exist on
the connected server. Discovery completeness and live engine/version capability
qualification remain provider-owned.
