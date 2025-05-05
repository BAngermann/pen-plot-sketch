import vsketch
import math


class Point:
  def __init__(self,x,y):
      self.x = x
      self.y = y
  def __eq__(self, value):
      d_sq = (self.x-value.x)**2 + (self.y-value.y)**2
      return(d_sq < 1e-20)
  def dist(self,value):
     return (self-value).length()
  def __sub__(self,other):
      return Point(self.x-other.x,self.y-other.y)
  def __add__(self,other):
      return Point(self.x+other.x,self.y+other.y)
  def length(self):
      return math.sqrt((self.x)**2 + (self.y)**2)
  def toUnit(self):
      scale = 1/self.length()
      return(Point(self.x*scale,self.y*scale))
  def normal(self,before,after):
      v1 = self-before
      v2 = after - self
      mean = (v1+v2).toUnit()
      return Point(mean.y,-mean.x)
  def scale(self,s):
      return Point(self.x*s,self.y*s)

class TreeringsSketch(vsketch.SketchClass):
    # Sketch parameters:
    n = vsketch.Param(50, min_value =20  )
    n_rings = vsketch.Param(20, min_value = 10  )
    r_start = vsketch.Param(0.5, min_value = 0.01  )
    linear_thickness = vsketch.Param(0.1, min_value = 0.01  )

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")

        n = self.n
        n_rings = self.n_rings
        ring = [Point(self.r_start*math.cos(i*2*math.pi/n  ),self.r_start*math.sin(i*2*math.pi/n)) for i in range(n)]
        growth = [Point(0,0) for i in range(n)]

        for year in range(n_rings):
            thickness = math.exp(vsk.randomGaussian()/1.5)*self.linear_thickness
            for i in range(n):
                p = ring[i]
                p_a = ring[(i+1)%n]
                p_b = ring[(i-1)%n]
                vsk.line(p.x,p.y,p_a.x,p_a.y )
                growth[i] = p.normal(p_b,p_a).scale(thickness*(0.1+0.5*vsk.noise(1+p.x,p.y,1)))
                #vsk.stroke(2)
                #vsk.line(p.x,p.y,p.x+growth[i].x,p.y+growth[i].y)
                #vsk.stroke(1)
            for i in range(n):  
                
                ring[i] = ring[i]+growth[i]


            


    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    TreeringsSketch.display()
