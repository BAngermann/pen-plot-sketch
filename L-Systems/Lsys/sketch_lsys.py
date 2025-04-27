import vsketch


class LsysSketch(vsketch.SketchClass):
    Axiom = vsketch.Param("F")
    Pred1 = vsketch.Param("F")
    Suc1 = vsketch.Param("F[+*F][-*F]")
    Pred2 = vsketch.Param("")
    Suc2 = vsketch.Param("")
    Draw = vsketch.Param("F")
    Move = vsketch.Param("f")
    TurnAngle = vsketch.Param(120)
    iterations = vsketch.Param(1)
    Scale = vsketch.Param(0.2, decimals = 3)
    TransformScale = vsketch.Param(0.5, decimals = 3)


    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")
        state = self.Axiom
        for i in range(self.iterations):
            newstate = ""
            for t in state:
                if t == self.Pred1:
                    newstate += self.Suc1
                elif t == self.Pred2:
                    newstate += self.Suc2
                else:
                    newstate += t
            state = newstate
        #print(state)
        vsk.scale(self.Scale)
        for t in state:
            if t in self.Draw:
                vsk.line(0,0,0,1)
                vsk.translate(0,1)
            elif t == "+":
                vsk.rotate(self.TurnAngle, degrees = True)
            elif t == "-":
                vsk.rotate(-self.TurnAngle, degrees = True)
            elif t == self.Move:
                vsk.translate(0,1)  
            elif t == "[":
                vsk.pushMatrix()
            elif t == "]":
                vsk.popMatrix()
            elif t == "*":
                vsk.scale(self.TransformScale)  

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    LsysSketch.display()
