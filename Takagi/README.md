# Takagi function based sketch

Sketch based on the Takagi functions and variants thereof. Each iteration is drawn separately.

The parameters have the following function:

<dl>
  <dt><strong>scale</strong></dt>
  <dd>Allows to draw each iteration to a value different from its actual height. The nex iteration will always start at the value unaffected by the scale parameter, thus a scale /lt one will show up as a gap inthe graph.</dt>
  <dt><strong>n_max</strong></dt>
  <dd>Number of iterations.</dd>
  <dt><strong>penWidth</strong></dt>
  <dd>Width of the pen.</dd>
  <dt><strong>stroke_iteration_scale</strong></dt>
  <dd>Increase to reduce the stroke width of earlier iterations.</dd>
  <dt><strong>w</strong></dt>
  <dd>Amount by which is each iteration is scaled with respect to the previous.</dd>
  <dt><strong>page_scale</strong></dt>
  <dd>Overall scale applied to the sketch.</dd>
  <dt><strong>negative_plot_offset</strong></dt>
  <dd>Offset of the negative part of the graph. (The remainder that needs to be added to arrive at a constant function)</dd>
  <dt><strong>plot_negative</strong></dt>
  <dd>Toggle if the negative part of the plot should be drawn.</dd>  
  <dt><strong>plot_positive</strong></dt>
  <dd>Toggle if the Takagi function should be drawn.</dd>  
</dl>
    
    glitch_w = vsketch.Param(True)
    negative_layer = vsketch.Param(False)
    iteration_layer = vsketch.Param(False)
    paper_size = vsketch.Param("a4",choices = ["a4","a5","a6","10cmx10cm"])
    title = vsketch.Param("")