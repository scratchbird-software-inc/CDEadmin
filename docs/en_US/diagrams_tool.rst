.. _diagrams_tool:

*********************
`Diagrams`:index:
*********************

.. note::

   Owner direction, 2026-11-06: ScratchRobin makes named diagrams with the
   Diagrams tool. Diagrams are DDN (Diagram Design Notation) documents; DDN
   renders and edits them. The default notation is crow's foot
   (``erd.crowfoot@1``). Added 2026-11-08.

The Diagrams tool keeps named diagrams as project assets. Open it from
*Tools > Diagrams* or from the *Diagrams* icon on the activity bar. *Tools >
New Diagram…* opens the same panel with the *New diagram* dialog.

Creating a diagram
==================

The *New diagram* dialog (form reference SR-F-010016) asks for:

* **Diagram name**: shown in the Diagrams panel, the Project Explorer and the
  diagram's title. It cannot contain line breaks.
* **Project**: a project you can edit, or *New project…*, which creates one
  (ID ``diagrams`` and name *Diagrams* unless you change them).
* **Notation**: the notation of the diagram's first view.

  * *Crow's foot ERD* (default): tables and views with their fields;
    relations carry crow's-foot cardinality marks.
  * *DDN relations graph*: the notation of ScratchRobin's catalog
    diagrams.
  * *Chen ERD*, *UML class diagram*, *Object-role model* and *Chebotko
    logical diagram* are listed but unavailable: ScratchRobin cannot yet
    map catalog objects into them.

A new diagram starts empty. Before it is stored, DDN verifies it. It then
opens in the DDN designer, where you can add elements and views, and save
new revisions.

The diagrams panel
==================

The Diagrams panel (form reference SR-F-010015) lists the diagrams in every
project you can open, grouped by project, with each diagram's notation.
Double-click a diagram to open it: in the DDN designer if you can edit the
project, otherwise in the read-only DDN viewer. Dashboard drafts and other
DDN assets are not diagrams and are not listed; they remain in the Project
Explorer.

A diagram is a project asset of type ``ddn-workspace`` whose metadata
records ``{"diagram": {"schema": "cdeadmin.diagram.v1", "notation": ...}}``.
