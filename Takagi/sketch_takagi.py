import vsketch

def s_fun(x,n,w):
    x = x * 2**n
    return min(x%1,(1-x)%1)*w**n

class TakagiSketch(vsketch.SketchClass):
    # Sketch parameters:
    scale = vsketch.Param(0.6)
    n_max = vsketch.Param(5)
    penWidth = vsketch.Param(0.2,decimals=2)
    w = vsketch.Param(0.5,decimals=3,min_value=0,max_value=1)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")
        vsk.pushMatrix()
        page_scale = 12
        vsk.scale(page_scale)
        
        vsk.penWidth(f'{self.penWidth}mm')
         
        x_points = [(x/2**(self.n_max+1))-1 for x in range(1+2**(self.n_max+1))]
        y = [0 for x in range(1+2**(self.n_max+1))]
     
        for n in range(self.n_max+1):
            y_add = [-s_fun(x,n,self.w) for x,y in zip(x_points,y)]

            y_plot = [y + self.scale*y_1 for y,y_1 in zip(y,y_add)]
            stroke = self.n_max+1-n

            vsk.strokeWeight(stroke)
            for i in range(len(x_points)):
                vsk.line(x_points[i],y[i],x_points[i],y_plot[i])
            y = [y + y_1 for y,y_1 in zip(y,y_add)]
            vsk.translate(0,-stroke*self.penWidth/10/page_scale)   
        vsk.popMatrix()


    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    TakagiSketch.display()
