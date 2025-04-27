import vsketch
import math

class ModuloMultiplication01Sketch(vsketch.SketchClass):
    r = vsketch.Param(1.0)
    page_margin_x = vsketch.Param(1.5,min_value=0)
    page_margin_y = vsketch.Param(1.5,min_value=0)
    plot_margin_x = vsketch.Param(.7,min_value=0)
    plot_margin_y = vsketch.Param(.7,min_value=0)
    n_min = vsketch.Param(2,min_value = 2)
    n_max = vsketch.Param(8,min_value = 2)
    text_scale = vsketch.Param(0.2, min_value = 0.01)
    
    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False, center = False)
        vsk.scale("cm")
        twopi = 6.28318530718
        y_text_gap = 3 * self.text_scale
        x_text_gap = 3 * self.text_scale
        multiplier = 2
        n = self.n_min
        vsk.translate( self.page_margin_x, self.page_margin_y)

        vsk.pushMatrix()
        vsk.translate(0,y_text_gap)
        for n in range(self.n_min,self.n_max+1):
            vsk.text(text = f'n={n}',x=-self.r,y=self.r,size = self.text_scale,mode = "transform",font = "futural")
            vsk.translate( 0, self.plot_margin_y + 2 * self.r)
        vsk.popMatrix()

        vsk.pushMatrix()
        vsk.translate(x_text_gap,0)
        for n in range(0,self.n_max+1):
            vsk.text(text = f'{n}',x=self.r,y=self.r,size = self.text_scale,mode = "transform",font = "futural",align = "center")
            vsk.translate(  self.plot_margin_x + 2 * self.r , 0)
        vsk.popMatrix()

        vsk.translate( 3 * self.text_scale, y_text_gap)
        vsk.translate( self.r, self.r)
         
        for n in range(self.n_min,self.n_max+1):

            print(f'n = {n}')
            mul_tabs = []
            for multiplier in range(0,n+1):
                mul_tabs.append(  frozenset([ frozenset([i, (i*multiplier)%n ] ) for i in range(0,n)] )   )
            
            equal_pairs = []
            for i in range(len(mul_tabs)):
                for j in range(i+1,len(mul_tabs)):
                    if mul_tabs[i] == mul_tabs[j]:
                        equal_pairs.append( set([i,j]) ) 
            print(f'redundant pairs: {len(equal_pairs)}, {n+1-len(equal_pairs)} remaining')

            for i,s in enumerate(equal_pairs):
                for s2 in equal_pairs[:i]:
                    if(len(s.intersection(s2))>0 ):
                        print(s)
                        print(s2)

            vsk.pushMatrix()
            for multiplier in range(0,n+1) :
                vsk.circle(0, 0, 2 * self.r)
                for i in range(0,n):
                    tpn = twopi/n
                    vsk.line(-self.r * math.cos(i*tpn),
                      self.r * math.sin(i * tpn),
                      -self.r * math.cos(((i * multiplier) % n) * tpn),
                      self.r * math.sin(((i * multiplier) % n) * tpn))

                vsk.translate( self.plot_margin_x + 2 * self.r, 0)
            vsk.popMatrix()
            vsk.translate( 0, self.plot_margin_y + 2 * self.r)


    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    ModuloMultiplication01Sketch.display()
