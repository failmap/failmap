# Concept
Color: red is often seen as a "no", "stop". For example in traffic.
The "F" is used to denote failure in the american grading system, which is the first letter of Fail Map.
The square is an abstraction of a map.


# Design
Dimensions:
20x20cm

Square shape:
16x16cm (using 2 cm padding)

Text:
Font: News Gothic MT Bold
Font size: 320pt
Value: Capital letter F
Placement: Center (perceptive)

Color:
Red

# Optimize
Round off the paths:
Settings: Extreme, with customization: 0 decimal places.
http://www.scriptcompress.com/SVG-minifier.htm

Then:
Remove: xmlns:xlink="http://www.w3.org/1999/xlink" (file does not contain xlinks)
Remove: version="1.1" (nobody uses this)
Remove: id="Layer_1" (there are no layers)
Remove: x="0px" y="0px" (implied)
Remove: viewBox="0 0 566.93 566.93" (??? can do without)
Remove: enable-background="new 0 0 566.93 566.93" (??? can do without)
Remove: xml:space="preserve" (??? can do without)
Remove: the last Z from the path, which is implied.
Remove: V206 from the end, as a path closes itself.
Remove: whitespace, newlines

Remove the decimals from Width and Height.

Reduce color bytes from "#ED1E24" to "red".

# Result
Resulting in an 156 byte logo, consisting of a single path and SVG bloat.
Whitespace is added for readability:

<svg xmlns="http://www.w3.org/2000/svg" width="567" height="567">
 <path fill="red" d="M56 56v454h454V56H56zM356 206h-99v63h57v41h-57V404h-47V165H356"/>
</svg>
