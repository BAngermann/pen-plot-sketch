import vsketch
import math

def s_fun(x,n,w):
    x = x * 2**n
    return 2*min(x%1,(1-x)%1)*w#**(n+1)


def logit(x):
    return( math.log(x/(1-x)))

def logistic(x):
    return(1/(1+math.exp(-x)))

class TakagiSketch(vsketch.SketchClass):
    # Sketch parameters:
    scale = vsketch.Param(0.6)
    n_max = vsketch.Param(5,min_value = 0)
    penWidth = vsketch.Param(0.2,decimals=2)
    stroke_iteration_scale = vsketch.Param(1,min_value =1, max_value=9)
    w = vsketch.Param(0.5,decimals=3,min_value=0,max_value=1)
    page_scale = vsketch.Param(12,decimals=1,min_value = 0.1,max_value=20)
    negative_plot_offset = vsketch.Param(1.05, min_value = 0.9,max_value = 3,decimals =3)
    plot_negative = vsketch.Param(True)
    plot_positive = vsketch.Param(True)
    glitch_w = vsketch.Param(True)
    negative_layer = vsketch.Param(False)
    iteration_layer = vsketch.Param(False)
    paper_size = vsketch.Param("a4",choices = ["a4","a5","a6","10cmx10cm"])
    title = vsketch.Param("")
    randomize = vsketch.Param(False)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size(self.paper_size, landscape=False)
        vsk.scale("cm")
        vsk.pushMatrix()
        vsk.scale(self.page_scale)
        
        vsk.penWidth(f'{self.penWidth}mm')
        print("********")
        x_points = [(x/2**(self.n_max+1))-1 for x in range(1+2**(self.n_max+1))]
        y = [0 for x in range(1+2**(self.n_max+1))]
        y_neg = [-self.negative_plot_offset for x in range(1+2**(self.n_max+1))]
        layer = 0
        w = self.w
        for n in range(self.n_max+1):

            neg_w = w
            if self.glitch_w:
                neg_w *= 0.5
            y_add = [-s_fun(x,n,w) for x,y in zip(x_points,y)]
            y_plot = [y + self.scale*y_1 for y,y_1 in zip(y,y_add)]
            stroke = math.ceil((self.n_max+1.-n)/self.stroke_iteration_scale)

            vsk.strokeWeight(stroke)
            if self.plot_positive:
                vsk.stroke(layer+1)
                vsk.translate(0,-stroke*self.penWidth/10/self.page_scale)
                for i in range(len(x_points)):
                    vsk.line(x_points[i],y[i],x_points[i],y_plot[i]+1e-6)
            y = [y + y_1 for y,y_1 in zip(y,y_add)]
            if self.iteration_layer:
                layer = (layer + 1) % 2
            # add a random term that is biased such that the final scale to be close to the expected scale
                        
            w_scale = logit(self.w)
            if self.randomize:
                expected_w = logit(self.w**(n+1))
                actual_w = logit(w)
                w_scale = w_scale + 0.8*(expected_w-actual_w)  +  1.5 * vsk.randomGaussian()
            w_scale = logistic(w_scale)
            w *= w_scale
            print(w)

        
        if self.plot_negative:
            if self.negative_layer:
                layer = 1
            for n in range(self.n_max+1):
                y_add = [-s_fun(x,n,w) for x,y in zip(x_points,y)]
                y_neg_add = [ (neg_w**(n+1)+y_1) for y_neg,y_1 in zip(y_neg,y_add)]
                y_neg_plot = [y_neg + self.scale * y_1 for y_neg,y_1 in zip(y_neg,y_neg_add)  ]
                stroke = math.ceil((self.n_max+1.-n)/self.stroke_iteration_scale)
                vsk.strokeWeight(stroke)
                vsk.stroke(layer+1)
                vsk.translate(0,stroke*self.penWidth/10/self.page_scale)
                for i in range(len(x_points)):
                    vsk.line(x_points[i],y_neg[i],x_points[i],y_neg_plot[i]+1e-6)
                y_neg = [y_neg + y_1 for y_neg,y_1 in zip(y_neg,y_neg_add)]
                if self.iteration_layer:
                    layer = (layer + 1) % 2
               
        vsk.popMatrix()
        vsk.textMode("label")
        vsk.text(text = self.title, x=-1,y=1,size = "8pt",align='right')

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("")


if __name__ == "__main__":
    TakagiSketch.display()
