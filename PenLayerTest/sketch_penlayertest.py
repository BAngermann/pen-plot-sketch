import vsketch


class PenlayertestSketch(vsketch.SketchClass):
    # Sketch parameters:
    numberOfPens = vsketch.Param(4,min_value =1, max_value=9)
    numberOfLines = vsketch.Param(1,min_value =1, max_value=9)
    penNames = vsketch.Param("Separate\nnames\nwith\nnewlines")
    penWidth = vsketch.Param(0.2,decimals=2)
     
    def paintLine(self,vsk,unitsize,horizontal = True):
        pen_mm = 0.1*self.penWidth
        offset = 0.5*unitsize-pen_mm*(self.numberOfLines-1)/2
        start = 0.1 * unitsize
        end = 0.9 * unitsize
        for l in range(self.numberOfLines):
            pen_pos = offset+l*pen_mm
            if horizontal:
                vsk.line(start,pen_pos,end,pen_pos)
            else:
                vsk.line(pen_pos,start,pen_pos,end)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")
        stroke = 2
        penNames = self.penNames.splitlines()
        penNames += [''] * (self.numberOfPens - len(penNames))
        unitsize = (18/self.numberOfPens)-1
        gapsize =  unitsize+0.8
        vsk.pushMatrix()
        for row in range(self.numberOfPens):
            
            vsk.pushMatrix()
            vsk.stroke(1)
            vsk.text(text=penNames[row],x = -.5, y = 0.5*unitsize,size = .2,align = "right")
            vsk.stroke(stroke)
            for col in range(self.numberOfPens):
                self.paintLine(vsk,unitsize,True)
                vsk.translate(gapsize,0)
            vsk.popMatrix()
            vsk.translate(0,1.2*gapsize)
            stroke += 1
        vsk.popMatrix()

        for col in range(self.numberOfPens):
            vsk.pushMatrix()
            vsk.stroke(1)
            vsk.pushMatrix()
            vsk.translate(1+.5*unitsize,0)
            vsk.rotate(-90,degrees = True)
            vsk.text(text=penNames[col],y = -1, x = 0.5*unitsize,size = .2,align = "left")
            vsk.popMatrix()
            vsk.stroke(stroke)
            for row in range(self.numberOfPens):
                self.paintLine(vsk,unitsize,False)
                vsk.translate(0,1.2*gapsize)
            vsk.popMatrix()
            vsk.translate(gapsize,0)
            stroke += 1

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    PenlayertestSketch.display()
