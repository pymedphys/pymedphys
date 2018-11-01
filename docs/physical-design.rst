[WIP] Physical File Structure and Design
========================================

Cyclic dependencies and the justification of file structure

If package A depends on package B, and package B depends on package C, it is
important that package C does not then depend on package A. This is called a
cyclic dependency. It causes issues in dependency logic and can be avoided
by purposefully designing how the packages depend on one another.

Ideally library packages are split up module by module based upon single tasks
that each library achieves. By having a very large number of small single
purpose modules the dependency tree can become very complicated. Complicated
dependency trees do not scale. As a result the inter dependencies between
library packages is tightly regulated. The modules themselves need to be
designed and programmed with these restrictions in mind.

The physical design of the module dependencies is inspired by
John Lakos at Bloomberg, writer of Large-Scale C++ Software Design. He
describes this methodology in a talk he gave which is available on YouTube.

For an overview of its use see:

> <https://youtu.be/NrARQ7rHV-c?t=2898>

For some details on the level structure basics see

> <https://youtu.be/QjFpKJ8Xx78?t=41m7s>

And lastly for a bit more context rewind back to:

> <https://youtu.be/QjFpKJ8Xx78?t=32m50s>

### Level 1

Level 1 packages are the foundation library packages.

These packages SHALL NOT depend on any internal package. They MAY however
depend on external packages (Level 0).

Given that these Level 1 packages are foundation packages their external
packages SHOULD only ever be those that are in wide use and are highly
supported within the python community. Examples of reasonable external packages
to be used are numpy, scipy, and pandas.

### Level 2

Level 2 packages.

The internal packages that Level 2 packages depend on SHALL only be Level 1
packages or external packages as long as those external
packages don't intern depend on one defined within this group.

### Level 3

Level 3 packages.

The internal packages that these depend on SHALL only be Level 1 or Level 2.
They MAY also depend external packages as long as those external
packages don't intern depend on one defined within this group.