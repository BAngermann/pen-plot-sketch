import vsketch
import math

class ModuloMultiplication01Sketch(vsketch.SketchClass):
    r = vsketch.Param(4.0)
    multiplier = vsketch.Param(8)
    n = vsketch.Param(500)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("10cm","10cm", landscape=False)
        vsk.scale("cm")
        twopi = 6.28318530718
        vsk.circle(0, 0, 2 * self.r)
        
        for i in range(0,self.n):
            tpn = twopi/self.n
            vsk.line(-self.r * math.cos(i*tpn),
                     self.r * math.sin(i * tpn),
                     -self.r * math.cos(((i * self.multiplier) % self.n) * tpn),
                     self.r * math.sin(((i * self.multiplier) % self.n) * tpn))
        vsk.text(text = f'n={self.n}',x=-self.r,y=self.r,size = "0.5",mode = "transform",font = "futural")
        vsk.text(text = f'x={self.multiplier}',x=self.r,y=self.r,size = "0.5",mode = "transform",font = "futural",align="right")


    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    ModuloMultiplication01Sketch.display()
