import vsketch
import math

def s_fun(x,n,w):
    x = x * 2**n
    return min(x%1,(1-x)%1)*w**n

class TakagiSketch(vsketch.SketchClass):
    # Sketch parameters:
    scale = vsketch.Param(0.6)
    n_max = vsketch.Param(5)
    penWidth = vsketch.Param(0.2,decimals=2)
    stroke_iteration_scale = vsketch.Param(1,min_value =1, max_value=9)
    w = vsketch.Param(0.5,decimals=3,min_value=0,max_value=1)
    page_scale = vsketch.Param(12,decimals=1,min_value = 0.1,max_value=20)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")
        vsk.pushMatrix()
        vsk.scale(self.page_scale)
        
        vsk.penWidth(f'{self.penWidth}mm')
         
        x_points = [(x/2**(self.n_max+1))-1 for x in range(1+2**(self.n_max+1))]
        y = [0 for x in range(1+2**(self.n_max+1))]
     
        for n in range(self.n_max+1):
            y_add = [-s_fun(x,n,self.w) for x,y in zip(x_points,y)]

            y_plot = [y + self.scale*y_1 for y,y_1 in zip(y,y_add)]
            stroke = math.ceil((self.n_max+1.-n)/self.stroke_iteration_scale)

            vsk.strokeWeight(stroke)
            for i in range(len(x_points)):
                vsk.line(x_points[i],y[i],x_points[i],y_plot[i])
            y = [y + y_1 for y,y_1 in zip(y,y_add)]
            vsk.translate(0,-stroke*self.penWidth/10/self.page_scale)   
        vsk.popMatrix()


    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    TakagiSketch.display()
