import vsketch
import math
import numpy as np


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
    n_segments = vsketch.Param(250, min_value =20  )
    n_rings = vsketch.Param(20, min_value = 10  )
    r_start = vsketch.Param(0.1, min_value = 0.01  )
    linear_thickness = vsketch.Param(0.1, min_value = 0.01  )
    relaxation_increment = vsketch.Param(0.1, min_value = 0.01,max_value = 0.5  )
    relaxation_iterations = vsketch.Param(2, min_value = 0  )
    fixed_growth = vsketch.Param(0.1, min_value = 0.01,max_value = 1  )
    growth_noise = vsketch.Param(0.5, min_value = 0,max_value = 1  )
    noise_offset_x= vsketch.Param(1.0, min_value = -3,max_value = 3,step = 0.1 ,decimals = 2 )
    slice_thickness = vsketch.Param(0.1, min_value = 0.01,max_value = 1  )
    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")

        n = self.n_segments
        n_rings = self.n_rings
        yearly_growth = [math.exp(vsk.randomGaussian()/1.5)*self.linear_thickness for year in range(n_rings)]
        num_cols = 3
        slice = 0
        for columns in range(num_cols):
            vsk.translate(sum(yearly_growth),0)
            ring = [Point(self.r_start*math.cos(i*2*math.pi/n  ),self.r_start*math.sin(i*2*math.pi/n)) for i in range(n)]
            growth = [Point(0,0) for i in range(n)]

            for year in range(n_rings):
                thickness = yearly_growth[year]
                for i in range(n):
                    p = ring[i]
                    p_a = ring[(i+1)%n]
                    p_b = ring[(i-1)%n]
                    vsk.line(p.x,p.y,p_a.x,p_a.y )
                    noise_value = vsk.noise(self.noise_offset_x+p.x,p.y,slice*self.slice_thickness)
                    growth[i] = p.normal(p_b,p_a).scale(thickness*(self.fixed_growth+self.growth_noise*noise_value))
                    #vsk.stroke(2)
                    #vsk.line(p.x,p.y,p.x+growth[i].x,p.y+growth[i].y)
                    #vsk.stroke(1)
                for i in range(n):  
                    ring[i] = ring[i]+growth[i]
                for i in range(self.relaxation_iterations):
                    distances = [ring[i].dist(ring[(i+1)%n]) for i in range(n)]
                    mean_dist = sum(distances)/n
                    for j in range(n):
                        if distances[j] < mean_dist:
                    # depending which adjacent segment is longer, move the vertex along the segment to increase the length of the segment
                            if distances[(j+1)%n] > distances[(j-1)%n] :
                                old = ring[(j+1)%n]
                                next = ring[(j+2)%n]
                                move = (next - old).scale(self.relaxation_increment)
                                ring[(j+1)%n] = old + move
                            else:
                                old = ring[j]
                                next = ring[(j-1)%n]
                                move = (next - old).scale(self.relaxation_increment)
                                ring[j] = old + move
            slice += 1



            


    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    TreeringsSketch.display()
