import vsketch


class PlottertestSketch(vsketch.SketchClass):
    columns = vsketch.Param(20,min_value = 0,max_value=200)
    col_width = vsketch.Param(0.3,min_value = 0.1,max_value=20)
    rows = vsketch.Param(30,min_value = 0,max_value=200)
    row_width = vsketch.Param(0.3,min_value = 0.1,max_value=20)
    

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False,center = False)
        vsk.scale("cm")
        height_margin = 1
        width_margin = 1
        col_width = self.col_width
        row_width = self.row_width
 
        page = (self._vsk._document._metadata['vp_page_size'])
        width = page[0]/96*2.54
        height = page[1]/96*2.54
        vsk.rect(width_margin, height_margin,width-2*width_margin,height-2*height_margin)
        if self.columns > 0:
            col_step = (width-2*width_margin)/(self.columns+1)
            for i in range(self.columns):
                vsk.rect(x=width_margin - col_width/2 + (i+1) * col_step,
                y=height_margin,
                w=col_width,
                h=height-2*height_margin,
                tl=col_width,br=col_width)
        if self.rows > 0:
            row_step = (height-2*height_margin)/(self.rows+1)
            for i in range(self.rows):
                vsk.rect(x=width_margin ,
                y=height_margin- row_width/2 + (i+1) * row_step,
                w=width-2*width_margin,
                h=row_width,
                tr=row_width,bl=row_width)


    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("")


if __name__ == "__main__":
    PlottertestSketch.display()
 